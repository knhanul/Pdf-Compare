import sys
import fitz  # PyMuPDF
import re
from difflib import SequenceMatcher
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QScrollArea, QSizePolicy, QMessageBox
)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor
from PyQt6.QtCore import Qt, QSize, QPoint, QRect

# --- 1. Core Logic: Section Matching and Diff Detection ---

def normalize_text(text):
    """제목 정규화: 숫자, 로마 숫자, 공백, 특수문자 제거 및 소문자 변환"""
    # 1. 특수문자 및 구두점 제거 (한글, 영어, 숫자 제외)
    text = re.sub(r'[^\w\s가-힣]', '', text)
    # 2. 로마 숫자 제거 (I, II, III, IV, V, VI, VII, VIII, IX, X)
    text = re.sub(r'\b[IVX]+\b', '', text, flags=re.IGNORECASE)
    # 3. 공백 제거
    text = re.sub(r'\s+', '', text)
    # 4. 소문자 변환
    return text.lower()

def is_placeholder_diff(text_a, text_b):
    """
    플레이스홀더 변경으로 인한 차이인지 확인합니다.
    템플릿(A)에 플레이스홀더 패턴이 있고, 생성본(B)에 실제 데이터가 채워진 경우 True 반환.
    """
    # 알려진 플레이스홀더 패턴 (정규식)
    # 사용자가 요청한 패턴: ○○○, x.xx%, xxx 등
    placeholder_patterns = [
        r'○○○', r'xxx', r'x\.xx%', r'××세', r'××××', r'O / O', r'OOOOOOOOOOOO',
        r'\[\s*보장성보험\s*\]', r'\[\s*표준형\s*\]', r'\[\s*해약환급금\s*50\%\s*지급형\s*\]',
        r'(\d{4}년\s*\d{2}월\s*\d{2}일\s*\d{2}:\d{2})', # 날짜/시간
        r'(\d{3}-\d{4}-\d{4})', # 전화번호
        r'(\d{1,2}/\d{1,2})', # 날짜 (예: 9/15)
        r'(\d{1,2}세)', # 나이
        r'[가-힣]{2,4}', # 이름 (UQREPO, 화임김, 동생치 등)
        r'(\d{1,3}(,\d{3})*원)', # 금액 (1,000만원, 30,000,000원 등)
        r'(\d{1,2}\.\d{2}\%)', # 이율 (x.xx%, 2.25% 등)
        r'(\d{1,3}(,\d{3})*)\s*만원', # 금액 (1,000만원)
        r'(\d{1,3}(,\d{3})*)\s*원', # 금액 (10,000,000원)
        r'(\d{1,2}\.\d{2})', # 숫자 (2.25)
        r'(\d{1,4})', # 숫자 (2402)
        r'[A-Z]{4,6}', # 영문 대문자 (UQREPO)
    ]
    
    # A 텍스트에 플레이스홀더 패턴이 포함되어 있는지 확인
    is_a_placeholder = False
    for pattern in placeholder_patterns:
        if re.search(pattern, text_a):
            is_a_placeholder = True
            break
            
    # B 텍스트에 플레이스홀더 패턴이 포함되어 있는지 확인
    is_b_placeholder = False
    for pattern in placeholder_patterns:
        if re.search(pattern, text_b):
            is_b_placeholder = True
            break

    # A가 플레이스홀더를 포함하고, B가 A와 다르다면 (즉, 채워졌다면)
    if is_a_placeholder and text_a.strip() != text_b.strip():
        return True
        
    # B가 플레이스홀더를 포함하고, A가 B와 다르다면 (즉, A가 채워진 값이라면)
    # 이 경우는 템플릿이 B일 때를 대비한 것이지만, 현재는 A가 템플릿이므로 A만 검사
    # if is_b_placeholder and text_a.strip() != text_b.strip():
    #     return True
    
    return False

def extract_text_blocks(pdf_doc):
    """PyMuPDF를 사용하여 페이지별 텍스트 블록과 좌표를 추출합니다."""
    all_blocks = []
    for page_num in range(len(pdf_doc)):
        page = pdf_doc.load_page(page_num)
        # 'text' 모드로 텍스트 블록 추출 (bbox 포함)
        blocks = page.get_text("blocks")
        
        page_blocks = []
        for block in blocks:
            # block: (x0, y0, x1, y1, text, block_no, block_type)
            bbox = block[:4]
            text = block[4].strip()
            
            if text:
                page_blocks.append({
                    'page': page_num,
                    'bbox': bbox,
                    'text': text,
                    'normalized_text': normalize_text(text)
                })
        all_blocks.append(page_blocks)
    return all_blocks

def find_best_match(target_block, source_blocks):
    """
    주어진 블록(target_block)과 가장 유사한 블록을 source_blocks에서 찾습니다.
    섹션 매칭을 위해 normalized_text를 사용합니다.
    """
    best_score = -1
    best_match = None
    
    target_norm = target_block['normalized_text']
    
    for block in source_blocks:
        source_norm = block['normalized_text']
        
        # SequenceMatcher를 사용하여 유사도 계산
        matcher = SequenceMatcher(None, target_norm, source_norm)
        score = matcher.ratio()
        
        if score > best_score:
            best_score = score
            best_match = block
            
    # 유사도 임계값 설정 (예: 0.8 이상)
    if best_score >= 0.8:
        return best_match
    return None

def compare_text_blocks(block_a, block_b):
    """
    두 텍스트 블록을 비교하여 차이점 유형을 반환합니다.
    'modified', 'placeholder', 'same'
    """
    text_a = block_a['text']
    text_b = block_b['text']
    
    if text_a == text_b:
        return 'same'
    
    # 플레이스홀더 변경으로 인한 차이인지 확인
    if is_placeholder_diff(text_a, text_b):
        return 'placeholder'
        
    # 실제 내용이 다름
    return 'modified'

def perform_comparison(blocks_a, blocks_b):
    """
    두 PDF의 텍스트 블록을 비교하고 하이라이트 데이터를 생성합니다.
    또한, 동기화 스크롤을 위한 매칭 정보도 반환합니다.
    """
    diff_data_a = {} # {page_num: [(bbox, color_name)]}
    diff_data_b = {}
    
    # A와 B의 모든 블록을 하나의 리스트로 만듭니다.
    flat_blocks_a = [block for page in blocks_a for block in page]
    flat_blocks_b = [block for page in blocks_b for block in page]
    
    # 동기화 스크롤을 위한 매칭 정보: {A_block_index: B_block_index}
    sync_map = {}
    
    # 1. A를 기준으로 B와 매칭되는 블록 찾기 (Modified, Placeholder, Deleted)
    matched_b_indices = set()
    
    for i, block_a in enumerate(flat_blocks_a):
        best_match_b = find_best_match(block_a, flat_blocks_b)
        
        if best_match_b:
            # 매칭된 블록 인덱스 기록
            j = flat_blocks_b.index(best_match_b)
            matched_b_indices.add(j)
            sync_map[i] = j
            
            # 텍스트 비교
            diff_type = compare_text_blocks(block_a, best_match_b)
            
            if diff_type == 'modified':
                # [다름] (Modified): 노란색 하이라이트
                page_a = block_a['page']
                page_b = best_match_b['page']
                
                diff_data_a.setdefault(page_a, []).append((block_a['bbox'], "yellow"))
                diff_data_b.setdefault(page_b, []).append((best_match_b['bbox'], "yellow"))
            
            # 'placeholder'와 'same'은 하이라이트하지 않음
            
        else:
            # [삭제] (Deleted): A에만 존재. 빨간색 하이라이트
            page_a = block_a['page']
            diff_data_a.setdefault(page_a, []).append((block_a['bbox'], "red"))

    # 2. B에만 존재하는 블록 찾기 (Added)
    for j, block_b in enumerate(flat_blocks_b):
        if j not in matched_b_indices:
            # [추가] (Added): B에만 존재. 초록색 하이라이트
            page_b = block_b['page']
            diff_data_b.setdefault(page_b, []).append((block_b['bbox'], "green"))
            
    return diff_data_a, diff_data_b, flat_blocks_a, flat_blocks_b, sync_map

# --- 2. GUI Implementation: PDF Viewer and Diff Highlighting ---

class PDFViewer(QScrollArea):
    """PDF 페이지를 이미지로 렌더링하고 스크롤하는 뷰어"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label = QLabel()
        self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setWidget(self.image_label)
        self.pdf_doc = None
        self.page_images = []
        self.current_page = 0
        self.diff_data = {} # {page_num: [(bbox, color_name)]}
        self.scale = 1.5 # 렌더링 스케일
        
    def load_pdf(self, path):
        try:
            self.pdf_doc = fitz.open(path)
            self.page_images = []
            for i in range(len(self.pdf_doc)):
                self.page_images.append(self.render_page_to_image(i))
            self.current_page = 0
            self.show_page(self.current_page)
            return True
        except Exception as e:
            print(f"Error loading PDF: {e}")
            self.pdf_doc = None
            self.image_label.clear()
            return False

    def render_page_to_image(self, page_num):
        """PyMuPDF를 사용하여 페이지를 QImage로 렌더링"""
        page = self.pdf_doc.load_page(page_num)
        pix = page.get_pixmap(matrix=fitz.Matrix(self.scale, self.scale))
        
        # QImage로 변환
        img = QImage(
            pix.samples, pix.width, pix.height, pix.stride, 
            QImage.Format.Format_RGB888 if pix.alpha == 0 else QImage.Format.Format_RGBA8888
        ).copy() # 복사본을 만들어야 안전하게 그릴 수 있음
        return img

    def show_page(self, page_num):
        if self.pdf_doc and 0 <= page_num < len(self.pdf_doc):
            self.current_page = page_num
            # 원본 이미지를 복사하여 하이라이트를 그립니다.
            img = self.page_images[page_num].copy()
            
            # 하이라이트 그리기
            if page_num in self.diff_data:
                painter = QPainter(img)
                for bbox, color_name in self.diff_data[page_num]:
                    color = QColor(color_name)
                    color.setAlpha(128) # 투명도 설정
                    painter.setBrush(color)
                    painter.setPen(Qt.PenStyle.NoPen)
                    
                    # bbox는 PDF 좌표계 (x0, y0, x1, y1)
                    # QImage 좌표계로 변환 (scale=1.5 가정)
                    x0, y0, x1, y1 = bbox
                    rect = QRect(
                        int(x0 * self.scale), 
                        int(y0 * self.scale), 
                        int((x1 - x0) * self.scale), 
                        int((y1 - y0) * self.scale)
                    )
                    painter.drawRect(rect)
                painter.end()
                
            self.image_label.setPixmap(QPixmap.fromImage(img))
            self.image_label.adjustSize()
            
    def set_diff_data(self, diff_data):
        self.diff_data = diff_data
        self.show_page(self.current_page) # 현재 페이지 다시 그리기
        
    def get_page_height(self, page_num):
        """특정 페이지의 렌더링된 높이를 반환합니다."""
        if self.pdf_doc and 0 <= page_num < len(self.pdf_doc):
            page = self.pdf_doc.load_page(page_num)
            return page.rect.height * self.scale
        return 0

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("상품설명서 시각적 검증 GUI")
        self.setGeometry(100, 100, 1200, 800)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # 1. 파일 로드 및 비교 버튼
        self.control_layout = QHBoxLayout()
        
        self.btn_load_a = QPushButton("템플릿 열기 (A)")
        self.btn_load_b = QPushButton("생성본 열기 (B)")
        self.btn_compare = QPushButton("비교 시작")
        
        self.btn_load_a.clicked.connect(lambda: self.load_file('A'))
        self.btn_load_b.clicked.connect(lambda: self.load_file('B'))
        self.btn_compare.clicked.connect(self.start_comparison)
        
        self.control_layout.addWidget(self.btn_load_a)
        self.control_layout.addWidget(self.btn_load_b)
        self.control_layout.addWidget(self.btn_compare)
        
        self.main_layout.addLayout(self.control_layout)
        
        # 2. PDF 뷰어 패널
        self.viewer_layout = QHBoxLayout()
        
        self.viewer_a = PDFViewer()
        self.viewer_b = PDFViewer()
        
        viewer_a_widget = QWidget()
        viewer_a_layout = QVBoxLayout(viewer_a_widget)
        viewer_a_layout.addWidget(QLabel("템플릿 (A)"))
        viewer_a_layout.addWidget(self.viewer_a)
        
        viewer_b_widget = QWidget()
        viewer_b_layout = QVBoxLayout(viewer_b_widget)
        viewer_b_layout.addWidget(QLabel("생성본 (B)"))
        viewer_b_layout.addWidget(self.viewer_b)
        
        self.viewer_layout.addWidget(viewer_a_widget)
        self.viewer_layout.addWidget(viewer_b_widget)
        
        self.main_layout.addLayout(self.viewer_layout)
        
        # 초기 파일 경로 설정 (샌드박스용)
        self.pdf_path_a = "/home/ubuntu/upload/기초서류_상품설명서.pdf"
        self.pdf_path_b = "/home/ubuntu/upload/상품설명서_2종_비갱신형.pdf"
        
        # 비교 결과 저장 변수
        self.flat_blocks_a = []
        self.flat_blocks_b = []
        self.sync_map = {} # {A_block_index: B_block_index}
        
        # 동기화 스크롤 연결 (핵심 기능)
        self.viewer_a.verticalScrollBar().valueChanged.connect(lambda value: self.sync_scroll(value, 'A'))
        self.viewer_b.verticalScrollBar().valueChanged.connect(lambda value: self.sync_scroll(value, 'B'))
        
        # 초기 파일 로드
        self.viewer_a.load_pdf(self.pdf_path_a)
        self.viewer_b.load_pdf(self.pdf_path_b)

    def load_file(self, viewer_id):
        # 샌드박스 환경에서는 QFileDialog 대신 미리 지정된 경로를 사용합니다.
        if viewer_id == 'A':
            path = self.pdf_path_a
            if self.viewer_a.load_pdf(path):
                print(f"템플릿 (A) 파일 로드 완료: {path}")
            else:
                print("템플릿 (A) 파일 로드 실패")
        elif viewer_id == 'B':
            path = self.pdf_path_b
            if self.viewer_b.load_pdf(path):
                print(f"생성본 (B) 파일 로드 완료: {path}")
            else:
                print("생성본 (B) 파일 로드 실패")

    def get_block_index_from_scroll(self, viewer, scroll_value):
        """스크롤 위치를 기반으로 현재 보고 있는 텍스트 블록의 인덱스를 찾습니다."""
        
        # 현재 페이지 번호와 페이지 내 스크롤 위치 계산
        current_page = viewer.current_page
        
        # 현재 페이지의 시작 Y 좌표 (렌더링된 이미지 기준)
        page_start_y = 0
        for i in range(current_page):
            page_start_y += viewer.get_page_height(i)
            
        # 페이지 내 스크롤 위치 (렌더링된 이미지 기준)
        scroll_y_on_page = scroll_value - page_start_y
        
        # PDF 좌표계로 변환 (스케일 역산)
        pdf_y = scroll_y_on_page / viewer.scale
        
        # 해당 페이지의 텍스트 블록 중 가장 가까운 블록 찾기
        flat_blocks = self.flat_blocks_a if viewer == self.viewer_a else self.flat_blocks_b
        
        # flat_blocks에서 현재 페이지의 블록만 필터링
        page_blocks = [(i, block) for i, block in enumerate(flat_blocks) if block['page'] == current_page]
        
        for i, block in page_blocks:
            # 블록의 상단 Y 좌표 (PDF 좌표계)
            block_top_y = block['bbox'][1]
            
            if block_top_y * viewer.scale >= scroll_y_on_page:
                return i
        
        # 찾지 못하면 현재 페이지의 첫 블록 또는 마지막 블록 반환
        if page_blocks:
            return page_blocks[0][0] # 페이지의 첫 블록 인덱스
        
        return -1

    def get_scroll_from_block_index(self, viewer, block_index):
        """텍스트 블록 인덱스를 기반으로 스크롤 위치를 계산합니다."""
        flat_blocks = self.flat_blocks_a if viewer == self.viewer_a else self.flat_blocks_b
        
        if not flat_blocks or block_index < 0 or block_index >= len(flat_blocks):
            return 0
            
        block = flat_blocks[block_index]
        page_num = block['page']
        
        # 해당 페이지의 시작 Y 좌표 (렌더링된 이미지 기준)
        page_start_y = 0
        for i in range(page_num):
            page_start_y += viewer.get_page_height(i)
            
        # 블록의 상단 Y 좌표 (PDF 좌표계)
        block_top_y = block['bbox'][1]
        
        # 최종 스크롤 위치 (렌더링된 이미지 기준)
        scroll_value = page_start_y + (block_top_y * viewer.scale)
        
        return int(scroll_value)

    def sync_scroll(self, value, source_viewer_id):
        """
        섹션 매칭 기반 동기화 스크롤
        source_viewer_id: 'A' 또는 'B'
        """
        if not self.sync_map:
            # 비교가 시작되지 않았으면 단순 스크롤 동기화
            if source_viewer_id == 'A':
                self.viewer_b.verticalScrollBar().setValue(value)
            else:
                self.viewer_a.verticalScrollBar().setValue(value)
            return

        source_viewer = self.viewer_a if source_viewer_id == 'A' else self.viewer_b
        target_viewer = self.viewer_b if source_viewer_id == 'A' else self.viewer_a
        
        # 현재 스크롤 위치에 해당하는 텍스트 블록 인덱스 찾기
        source_block_index = self.get_block_index_from_scroll(source_viewer, value)
        
        if source_block_index == -1:
            return

        # 매칭되는 타겟 블록 인덱스 찾기
        if source_viewer_id == 'A':
            target_block_index = self.sync_map.get(source_block_index)
        else:
            # B -> A 매핑은 역으로 찾아야 함
            # A 블록 인덱스를 키로, B 블록 인덱스를 값으로 하는 딕셔너리이므로,
            # B 블록 인덱스(source_block_index)를 값으로 가지는 A 블록 인덱스를 찾아야 함
            target_block_index = next((a_idx for a_idx, b_idx in self.sync_map.items() if b_idx == source_block_index), None)

        if target_block_index is not None:
            # 타겟 블록의 위치로 스크롤 값 계산
            target_scroll_value = self.get_scroll_from_block_index(target_viewer, target_block_index)
            
            # 타겟 뷰어의 페이지를 먼저 변경
            target_block = self.flat_blocks_a[target_block_index] if source_viewer_id == 'B' else self.flat_blocks_b[target_block_index]
            target_viewer.show_page(target_block['page'])
            
            # 스크롤 이동
            target_viewer.verticalScrollBar().setValue(target_scroll_value)

    def start_comparison(self):
        if not self.viewer_a.pdf_doc or not self.viewer_b.pdf_doc:
            QMessageBox.warning(self, "경고", "PDF 파일을 모두 로드해야 비교를 시작할 수 있습니다.")
            return

        # 1. 텍스트 블록 추출
        blocks_a = extract_text_blocks(self.viewer_a.pdf_doc)
        blocks_b = extract_text_blocks(self.viewer_b.pdf_doc)
        
        # 2. 비교 로직 실행
        diff_data_a, diff_data_b, self.flat_blocks_a, self.flat_blocks_b, self.sync_map = perform_comparison(blocks_a, blocks_b)
        
        # 3. 뷰어에 하이라이트 데이터 적용
        self.viewer_a.set_diff_data(diff_data_a)
        self.viewer_b.set_diff_data(diff_data_b)
        
        QMessageBox.information(self, "비교 완료", "비교가 완료되었으며, 차이점이 시각적으로 하이라이트되었습니다.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    # sys.exit(app.exec()) # 샌드박스에서는 실행하지 않음
    print("GUI 애플리케이션 코드가 최종적으로 정리되었습니다.")
