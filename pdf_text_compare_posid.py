import sys
import fitz  # PyMuPDF
import re
import traceback
import os
import json
from datetime import datetime
from difflib import SequenceMatcher

# 버전 정보 (EXE 빌드 시 환경 변수로 설정 가능)
VERSION = os.environ.get('PDF_COMPARE_VERSION', '0.9.5') # 버전 1.4.0으로 수정 (결과바 UI 수정)
RELEASE_DATE = os.environ.get('PDF_COMPARE_RELEASE_DATE', datetime.now().strftime('%Y-%m-%d'))
DEVELOPER = '우체국금융개발원 디지털정보전략실 시스템품질팀'
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QScrollArea, QMessageBox, QTextEdit,
    QDialog, QDialogButtonBox
)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QIcon
from PyQt6.QtCore import Qt, QRect, QPoint


class VersionInfoDialog(QDialog):
    """버전 정보 다이얼로그"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("정보")
        self.setFixedSize(400, 250)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # 로고 이미지 (있는 경우)
        if os.path.exists('posid_logo.png'):
            logo_label = QLabel()
            logo_pixmap = QPixmap('posid_logo.png')
            logo_label.setPixmap(logo_pixmap.scaled(150, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo_label)
        
        # 프로그램 제목
        title_label = QLabel("<h2>PDF 텍스트 비교 프로그램</h2>")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # 버전 정보
        version_label = QLabel(f"<b>버전:</b> {VERSION}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)
        
        # 배포 일자
        release_label = QLabel(f"<b>배포 일자:</b> {RELEASE_DATE}")
        release_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(release_label)
        
        # 개발 기관
        developer_label = QLabel(f"<b>개발:</b> {DEVELOPER}")
        developer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        developer_label.setWordWrap(True)
        layout.addWidget(developer_label)
        
        layout.addStretch()
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        close_btn.setFixedHeight(35)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)


class ViewComparisonTextDialog(QDialog):
    """비교 텍스트 보기 다이얼로그 (텍스트 복사 기능 포함)"""
    
    def __init__(self, left_original, left_normalized, right_original, right_normalized, parent=None):
        super().__init__(parent)
        self.setWindowTitle("비교 텍스트 보기")
        self.resize(800, 600)
        
        # 레이아웃 설정
        layout = QVBoxLayout()
        
        # 텍스트 편집기 (읽기 전용)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        
        # HTML 컨텐츠 구성
        content = "<h3>📝 비교 텍스트 전문</h3>"
        content += "<hr>"
        
        # PDF 1
        content += "<h4>📄 PDF 1 - 원본 텍스트</h4>"
        content += f"<p>{left_original}</p>"
        content += "<h4>🔧 PDF 1 - 정규화된 텍스트</h4>"
        content += f"<p>{left_normalized}</p>"
        content += "<hr>"
        
        # PDF 2
        content += "<h4>📄 PDF 2 - 원본 텍스트</h4>"
        content += f"<p>{right_original}</p>"
        content += "<h4>🔧 PDF 2 - 정규화된 텍스트</h4>"
        content += f"<p>{right_normalized}</p>"
        content += "<hr>"
        
        content += "<p><i>💡 정규화: 줄바꿈, 공백, 구두점, 불릿 포인트, 한글 숫자 단위 차이 제거</i></p>"
        
        self.text_edit.setHtml(content)
        layout.addWidget(self.text_edit)
        
        # 버튼 레이아웃
        button_layout = QHBoxLayout()
        
        # 복사 버튼
        self.copy_all_btn = QPushButton("📋 전체 복사")
        self.copy_all_btn.clicked.connect(self.copy_all_text)
        self.copy_all_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 8px;")
        
        # 닫기 버튼
        self.close_btn = QPushButton("닫기")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setStyleSheet("padding: 8px;")
        
        button_layout.addWidget(self.copy_all_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.close_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def copy_all_text(self):
        """전체 텍스트를 클립보드에 복사"""
        # HTML 태그를 제거하고 순수 텍스트만 복사
        plain_text = self.text_edit.toPlainText()
        clipboard = QApplication.clipboard()
        clipboard.setText(plain_text)
        QMessageBox.information(self, "성공", "텍스트가 클립보드에 복사되었습니다.")


def compare_with_resync(words_left, words_right, lookahead=5):
    """
    재동기화 로직이 포함된 단어 비교 (개선된 버전)
    
    [개선 사항]
    - '단어 합치기' 로직이 일치 항목을 차이점으로 잘못 기록하던 버그 수정.
    - 합치기 성공 시, 차이점(difference)으로 기록하지 않고 동기화(sync)로 처리.
    
    Args:
        words_left: 왼쪽 단어 리스트
        words_right: 오른쪽 단어 리스트
        lookahead: 재동기화 시 탐색할 앞쪽 단어 개수
    
    Returns:
        differences: 차이점 리스트 [(type, left_idx, right_idx), ...]
    """
    differences = []
    i = 0  # 왼쪽 인덱스
    j = 0  # 오른쪽 인덱스
    
    while i < len(words_left) or j < len(words_right):
        # 둘 다 끝에 도달
        if i >= len(words_left) and j >= len(words_right):
            break
        
        # 왼쪽만 남음 (삭제)
        if i < len(words_left) and j >= len(words_right):
            differences.append(('delete', i, None))
            i += 1
            continue
        
        # 오른쪽만 남음 (추가)
        if i >= len(words_left) and j < len(words_right):
            differences.append(('insert', None, j))
            j += 1
            continue
        
        # 둘 다 있는 경우
        if words_left[i] == words_right[j]:
            # 일치
            i += 1
            j += 1
        else:
            # 불일치 발생 → 단어 합치기 및 재동기화 시도
            synced = False
            
            # 0. 단어 합치기 비교 (길이가 짧은 쪽의 다음 단어들을 공백 없이 합침)
            left_word = words_left[i]
            right_word = words_right[j]
            
            # 왼쪽이 더 짧은 경우: 왼쪽 단어들을 합쳐서 오른쪽과 비교
            if len(left_word) < len(right_word):
                for k in range(1, min(5, len(words_left) - i)):  # 최대 5개 단어까지 합침
                    combined = ''.join(words_left[i:i+k+1])  # 공백 없이 합침
                    if combined == right_word:
                        # 왼쪽 k개 단어가 합쳐서 오른쪽 1개 단어와 일치
                        
                        # [BUG FIX] 
                        # 이전 로직은 일치 항목을 'delete'로 기록했음.
                        # 일치 항목이므로 difference에 추가하지 않고 포인터만 이동.
                        # for idx in range(i, i + k):
                        #     differences.append(('delete', idx, None))
                        
                        i += k + 1
                        j += 1
                        synced = True
                        print(f"  → 단어 합치기 (왼쪽): {k+1}개 단어 합쳐서 일치, 현재 위치: L{i}, R{j}")
                        break
            
            # 오른쪽이 더 짧은 경우: 오른쪽 단어들을 합쳐서 왼쪽과 비교
            elif len(right_word) < len(left_word):
                for k in range(1, min(5, len(words_right) - j)):  # 최대 5개 단어까지 합침
                    combined = ''.join(words_right[j:j+k+1])  # 공백 없이 합침
                    if combined == left_word:
                        # 오른쪽 k개 단어가 합쳐서 왼쪽 1개 단어와 일치
                        
                        # [BUG FIX] 
                        # 이전 로직은 일치 항목을 'insert'로 기록했음.
                        # 일치 항목이므로 difference에 추가하지 않고 포인터만 이동.
                        # for idx in range(j, j + k):
                        #     differences.append(('insert', None, idx))
                        
                        i += 1
                        j += k + 1
                        synced = True
                        print(f"  → 단어 합치기 (오른쪽): {k+1}개 단어 합쳐서 일치, 현재 위치: L{i}, R{j}")
                        break
            
            if synced:
                continue
            
            # 1. 왼쪽에서 삭제된 경우: 오른쪽 현재 단어가 왼쪽 앞쪽에 있는지 확인
            for k in range(1, min(lookahead + 1, len(words_left) - i)):
                if words_left[i + k] == words_right[j]:
                    # 왼쪽 i ~ i+k-1 삭제
                    for idx in range(i, i + k):
                        differences.append(('delete', idx, None))
                    i += k
                    synced = True
                    print(f"  → 재동기화 (삭제): {k}개 단어 건너뜀, 현재 위치: L{i}, R{j}")
                    break
            
            if synced:
                continue
            
            # 2. 오른쪽에 추가된 경우: 왼쪽 현재 단어가 오른쪽 앞쪽에 있는지 확인
            for k in range(1, min(lookahead + 1, len(words_right) - j)):
                if words_left[i] == words_right[j + k]:
                    # 오른쪽 j ~ j+k-1 추가
                    for idx in range(j, j + k):
                        differences.append(('insert', None, idx))
                    j += k
                    synced = True
                    print(f"  → 재동기화 (추가): {k}개 단어 건너뜀, 현재 위치: L{i}, R{j}")
                    break
            
            if synced:
                continue
            
            # 3. 양쪽 모두 변경된 경우: 앞쪽에서 일치하는 지점 찾기
            best_match = None
            best_distance = float('inf')
            
            for k1 in range(1, min(lookahead + 1, len(words_left) - i)):
                for k2 in range(1, min(lookahead + 1, len(words_right) - j)):
                    if words_left[i + k1] == words_right[j + k2]:
                        distance = k1 + k2
                        if distance < best_distance:
                            best_distance = distance
                            best_match = (k1, k2)
            
            if best_match:
                k1, k2 = best_match
                # 왼쪽 i ~ i+k1-1 삭제, 오른쪽 j ~ j+k2-1 추가
                for idx in range(i, i + k1):
                    differences.append(('delete', idx, None))
                for idx in range(j, j + k2):
                    differences.append(('insert', None, idx))
                i += k1
                j += k2
                synced = True
                print(f"  → 재동기화 (변경): L+{k1}, R+{k2} 건너뜀, 현재 위치: L{i}, R{j}")
                continue
            
            # 4. 재동기화 실패 → 단순 변경으로 처리
            differences.append(('replace', i, j))
            i += 1
            j += 1
    
    return differences


class SelectableLabel(QLabel):
    """텍스트 선택이 가능한 커스텀 라벨"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.page_num = -1
        
    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self.selection_start = event.pos()
                self.selection_end = event.pos()
                self.is_selecting = True
                self.update()
        except Exception as e:
            print(f"❌ mousePressEvent 오류: {e}")
            
    def mouseMoveEvent(self, event):
        try:
            if self.is_selecting:
                self.selection_end = event.pos()
                self.update()
        except Exception as e:
            print(f"❌ mouseMoveEvent 오류: {e}")
            
    def mouseReleaseEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
                self.is_selecting = False
                self.selection_end = event.pos()
                
                parent = self.parent()
                while parent and not isinstance(parent, PDFViewer):
                    parent = parent.parent()
                if parent:
                    parent.on_selection_complete(self.page_num, self.get_selection_rect())
                
                self.update()
        except Exception as e:
            print(f"❌ mouseReleaseEvent 오류: {e}")
                
    def paintEvent(self, event):
        try:
            super().paintEvent(event)
            
            # 선택 영역이 있으면 표시 (선택 중이거나 선택 완료 후)
            if self.selection_start and self.selection_end:
                painter = QPainter(self)
                color = QColor(0, 120, 255, 100)
                painter.setBrush(color)
                pen = QPen(QColor(0, 0, 255), 3, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                rect = QRect(self.selection_start, self.selection_end).normalized()
                painter.drawRect(rect)
                painter.end()
        except Exception as e:
            print(f"❌ paintEvent 오류: {e}")
            
    def get_selection_rect(self):
        if self.selection_start and self.selection_end:
            return QRect(self.selection_start, self.selection_end).normalized()
        return None
    
    def has_selection(self):
        return self.selection_start is not None and self.selection_end is not None
    
    def clear_selection(self):
        """선택 영역 초기화"""
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.update()


class PDFViewer(QScrollArea):
    """PDF 뷰어 위젯"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(10)
        self.setWidget(self.container)
        
        self.pdf_doc = None
        self.page_labels = []
        self.page_images = []
        self.scale = 1.5
        
        self.selected_text = ""
        self.selected_page = -1
        self.selected_word_info = []
        
        self.word_highlights = {}
        # 텍스트 비교에 사용된 영역(옅은 하이라이트) 관리용
        self.selection_area_highlights = []
        
    def clear_pages(self):
        for i in reversed(range(self.vbox.count())):
            w = self.vbox.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.page_labels.clear()
        self.page_images.clear()
        
    def load_pdf(self, path):
        try:
            self.clear_pages()
            self.pdf_doc = fitz.open(path)
            
            for i in range(len(self.pdf_doc)):
                img = self.render_page_to_image(i)
                self.page_images.append(img)
                
                lbl = SelectableLabel(self.container)
                lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                lbl.page_num = i
                lbl.setMouseTracking(True)
                
                self.vbox.addWidget(lbl)
                self.page_labels.append(lbl)
                
            self.show_all_pages()
            return True
        except Exception as e:
            print(f"❌ PDF 로드 오류: {e}")
            traceback.print_exc()
            self.pdf_doc = None
            self.clear_pages()
            return False
            
    def render_page_to_image(self, page_num):
        page = self.pdf_doc.load_page(page_num)
        pix = page.get_pixmap(matrix=fitz.Matrix(self.scale, self.scale))
        fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
        return QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
        
    def show_all_pages(self):
        try:
            for page_num in range(len(self.page_images)):
                if page_num < len(self.page_labels):
                    if page_num in self.word_highlights:
                        highlighted_img = self.draw_word_highlights(self.page_images[page_num], page_num)
                        self.page_labels[page_num].setPixmap(QPixmap.fromImage(highlighted_img))
                    else:
                        self.page_labels[page_num].setPixmap(QPixmap.fromImage(self.page_images[page_num]))
                    self.page_labels[page_num].adjustSize()
        except Exception as e:
            print(f"❌ show_all_pages 오류: {e}")
            
    def zoom_in(self):
        self.scale *= 1.2
        self.reload_pages()
        
    def zoom_out(self):
        self.scale /= 1.2
        self.reload_pages()
        
    def reload_pages(self):
        if not self.pdf_doc:
            return
        
        try:
            for lbl in self.page_labels:
                lbl.clear_selection()
            
            self.page_images.clear()
            for i in range(len(self.pdf_doc)):
                img = self.render_page_to_image(i)
                self.page_images.append(img)
            
            self.show_all_pages()
            print("✓ 확대/축소 완료")
            
        except Exception as e:
            print(f"❌ reload_pages 오류: {e}")
        
    def on_selection_complete(self, page_num, rect):
        try:
            if rect and rect.width() > 5 and rect.height() > 5:
                # 새로운 영역을 선택하면 이전 비교 영역(옅은 파란색) 하이라이트 제거
                self.clear_selection_area_highlights()
                self.selected_page = page_num
                self.extract_text_with_word_info(page_num, rect)
                print(f"✓ 선택 완료: 페이지 {page_num}, 단어 수: {len(self.selected_word_info)}")
        except Exception as e:
            print(f"❌ on_selection_complete 오류: {e}")
    
    def is_meaningless_word(self, word):
        """의미 없는 단어 판별 (강화)"""
        # URL 제거
        url_patterns = ['http', 'https', 'www.', '.com', '.net', '.org', '.go.kr', '.kr', 'ftp://']
        for pattern in url_patterns:
            if pattern in word.lower():
                return True
        
        # 불릿 포인트 (확장)
        bullet_points = [
            'o', 'O',  # 알파벳 o
            '•', '●', '○', '◦', '⦿', '⦾',  # 원형
            '■', '□', '▪', '▫', '◾', '◽',  # 사각형
            '◆', '◇', '◈',  # 마름모
            '▶', '▷', '►', '▸',  # 화살표
            '※', '★', '☆', '✓', '✔', '✕', '✖',  # 기타 기호
            '-', '–', '—', '―',  # 하이픈류
            '→', '←', '↑', '↓',  # 화살표
            '①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩',  # 숫자 원
        ]
        if word.strip() in bullet_points:
            return True
        
        # 단일 문자 기호
        if len(word.strip()) == 1:
            char = word.strip()
            # 숫자, 한글, 영문이 아닌 단일 문자
            if not (char.isalnum() or self.is_korean(char)):
                return True
        
        # 순수 숫자만 있는 경우 (페이지 번호 등) - 2자리 이하
        if word.strip().isdigit() and len(word.strip()) <= 2:
            return True
        
        return False
    
    def is_korean(self, char):
        """한글 문자 판별"""
        return '가' <= char <= '힣' or 'ㄱ' <= char <= 'ㅎ' or 'ㅏ' <= char <= 'ㅣ'
    
    def normalize_korean_number(self, text):
        """
        한글 숫자 단위를 숫자로 변환
        예: "1,000만" → "10000000"
            "10,000,000" → "10000000"
        """
        # 한글 단위와 배수
        units = {
            '조': 1000000000000,
            '억': 100000000,
            '만': 10000
        }
        
        # 숫자 + 한글 단위 패턴 찾기
        for unit, multiplier in units.items():
            if unit in text:
                try:
                    # "1,000만원" → "1,000만" 추출
                    pattern = r'([0-9,]+)' + unit
                    match = re.search(pattern, text)
                    if match:
                        number_str = match.group(1)
                        # 쉼표 제거 후 숫자로 변환
                        number = int(number_str.replace(',', ''))
                        # 단위 곱하기
                        result = number * multiplier
                        # 원래 텍스트에서 해당 부분을 변환된 숫자로 교체
                        text = text.replace(match.group(0), str(result))
                except Exception as e:
                    # 변환 실패 시 원본 유지
                    pass
        
        # 남은 쉼표 제거 ("10,000,000" → "10000000")
        text = text.replace(',', '')
        
        return text
    
    def split_by_comma(self, word):
        """
        쉼표를 기준으로 단어 분리
        - 한글 문자 사이의 쉼표: "안녕,하세요" → ["안녕", "하세요"]
        - 공백 앞의 쉼표: "테스트, 확인" → ["테스트", "확인"]
        """
        # 쉼표로 분리
        parts = word.split(',')
        
        # 각 부분의 앞뒤 공백 제거
        result = []
        for part in parts:
            part = part.strip()
            if part:  # 빈 문자열이 아닌 경우만 추가
                result.append(part)
        
        # 분리된 부분이 없으면 원본 반환
        if not result:
            return [word]
        
        return result
    
    def normalize_word(self, word):
        """
        강화된 단어 정규화
        - 의미 없는 단어 제거
        - 한글 숫자 단위 변환
        - 구두점 제거
        - 소문자 변환
        - 공백 정규화
        """
        # 의미 없는 단어는 빈 문자열 반환
        if self.is_meaningless_word(word):
            return ''
        
        # 1. 한글 숫자 단위 변환 (구두점 제거 전에 먼저 수행)
        word = self.normalize_korean_number(word)
        
        # 2. 구두점과 특수문자 제거 (한글, 영문, 숫자만 유지)
        word = re.sub(r'[^\w\s가-힣]', '', word)
        
        # 3. 연속된 공백을 단일 공백으로
        word = re.sub(r'\s+', ' ', word)
        
        # 4. 소문자 변환
        word = word.lower()
        
        # 5. 앞뒤 공백 제거
        word = word.strip()
        
        return word
    
    def extract_text_with_word_info(self, page_num, rect):
        """선택 영역에서 텍스트와 단어 정보 추출 (좌표 정렬 로직 개선 v1.3.0)"""
        if not self.pdf_doc:
            return
        
        try:
            x0 = rect.x() / self.scale
            y0 = rect.y() / self.scale
            x1 = (rect.x() + rect.width()) / self.scale
            y1 = (rect.y() + rect.height()) / self.scale
            
            selection_rect = fitz.Rect(x0, y0, x1, y1)
            page = self.pdf_doc.load_page(page_num)
            
            words = page.get_text("words")
            
            # --- 수정된 로직 시작 ---
            
            # 1. 선택 영역 내의 단어들을 먼저 모두 수집
            selected_words_tuples = []
            for word_tuple in words:
                word_bbox = fitz.Rect(word_tuple[:4])
                # 선택 영역과 교차하는 단어만 수집
                if selection_rect.intersects(word_bbox):
                    selected_words_tuples.append(word_tuple)
            
            # 2. 수집된 단어들을 좌표 기준으로 정렬
            #    - key=lambda w: (int(w[1]), w[0])
            #    - int(w[1]): Y0 좌표 (줄) 기준. 소수점 버리고 정수화 (v1.3.0)
            #    - w[0]: X0 좌표 (칸) 기준 (왼쪽->오른쪽)
            sorted_words = sorted(selected_words_tuples, key=lambda w: (int(w[1]), w[0]))
            
            # 3. 정렬된 단어 리스트를 기반으로 최종 정보 생성
            self.selected_word_info = []
            for word_tuple in sorted_words:
                word_text = word_tuple[4]
                
                # 기존 쉼표 분리 로직 적용
                sub_words = self.split_by_comma(word_text)
                
                for sub_word in sub_words:
                    # 기존 정규화 로직 적용
                    normalized = self.normalize_word(sub_word)
                    
                    # 의미 있는 단어만 저장
                    if normalized:
                        self.selected_word_info.append({
                            'text': sub_word,
                            'normalized': normalized,
                            'bbox': word_tuple[:4],
                            'page': page_num
                        })
            
            # --- 수정된 로직 끝 ---
            
            print(f"✓ (좌표 정렬 v1.3.0) 추출된 단어 수: {len(self.selected_word_info)}")
            
        except Exception as e:
            print(f"❌ extract_text_with_word_info 오류: {e}")
            traceback.print_exc()
    
    def has_selection(self):
        """선택 영역이 있는지 확인"""
        return len(self.selected_word_info) > 0
    
    def clear_all_selections(self):
        """모든 선택 영역 제거"""
        for lbl in self.page_labels:
            lbl.clear_selection()
        self.selected_word_info.clear()
        self.selected_text = ""
        self.selected_page = -1
        # 비교 영역(옅은 하이라이트)도 같이 제거
        self.clear_selection_area_highlights()
        print("✓ 선택 해제")
    
    def add_word_highlight(self, page_num, bbox, color, word):
        """단어 하이라이트 추가"""
        if page_num not in self.word_highlights:
            self.word_highlights[page_num] = []
        self.word_highlights[page_num].append((bbox, color, word))

    def add_selection_area_highlight(self, page_num, bbox, color, word="compare-region"):
        """텍스트 비교에 사용된 영역을 표시하기 위한 옅은 하이라이트 추가"""
        # 나중에 쉽게 지우기 위해 별도 리스트에 관리
        self.selection_area_highlights.append((page_num, bbox, color, word))
        if page_num not in self.word_highlights:
            self.word_highlights[page_num] = []
        self.word_highlights[page_num].append((bbox, color, word))

    def clear_selection_area_highlights(self):
        """비교 영역(옅은 파란색) 하이라이트만 제거"""
        try:
            for page_num, bbox, color, word in self.selection_area_highlights:
                if page_num in self.word_highlights:
                    self.word_highlights[page_num] = [
                        (b, c, w)
                        for (b, c, w) in self.word_highlights[page_num]
                        if not (b == bbox and c == color and w == word)
                    ]
            self.selection_area_highlights.clear()
            self.show_all_pages()
        except Exception as e:
            print(f"❌ clear_selection_area_highlights 오류: {e}")
    
    def draw_word_highlights(self, image, page_num):
        """단어 하이라이트 그리기"""
        try:
            highlighted_img = image.copy()
            painter = QPainter(highlighted_img)
            
            if page_num in self.word_highlights:
                for bbox, color, word in self.word_highlights[page_num]:
                    try:
                        x0, y0, x1, y1 = bbox
                        x0 = int(x0 * self.scale)
                        y0 = int(y0 * self.scale)
                        x1 = int(x1 * self.scale)
                        y1 = int(y1 * self.scale)
                        
                        rect = QRect(x0, y0, x1 - x0, y1 - y0)
                        painter.fillRect(rect, color)
                    except Exception as e:
                        print(f"❌ 단어 '{word}' 그리기 오류: {e}")
                        continue
            
            painter.end()
            return highlighted_img
        except Exception as e:
            print(f"❌ draw_word_highlights 오류: {e}")
            return image
    
    def clear_highlights(self):
        """모든 하이라이트 제거"""
        self.word_highlights.clear()
        # 비교 영역(옅은 하이라이트) 목록도 같이 초기화
        self.selection_area_highlights.clear()
        self.show_all_pages()


class MainWindow(QMainWindow):
    """메인 윈도우"""
    
    def __init__(self):
        super().__init__()
        
        # f-string을 사용하여 VERSION 변수를 윈도우 타이틀에 포함
        self.setWindowTitle(f"PDF 텍스트 비교 (우체국금융개발원 시스템품질팀) - v{VERSION}")
        
        self.setGeometry(100, 100, 1600, 1000)
        
        # 아이콘 설정
        icon_path = os.path.join(os.path.dirname(__file__), "posid_logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # 상단 버튼
        top_button_layout = QHBoxLayout()
        
        # 버튼 생성
        self.btn_load_left = QPushButton("📄 PDF 1 열기")
        self.btn_load_right = QPushButton("📄 PDF 2 열기")
        self.btn_compare = QPushButton("🔍 텍스트 비교")
        self.btn_view_text = QPushButton("📝 비교 텍스트 보기")
        self.btn_clear_highlights = QPushButton("🧹 하이라이트 지우기")
        self.btn_version = QPushButton("ℹ️ 정보")
        
        # 버튼 크기 설정 (PDF 뷰어 영역 확대를 위해 높이 축소, 너비 확대)
        main_button_height = 38  # 50에서 38로 축소
        info_button_height = 28  # 32에서 28로 축소
        
        # 주요 버튼 크기 설정
        for btn in [self.btn_load_left, self.btn_load_right, self.btn_compare, 
                    self.btn_view_text, self.btn_clear_highlights]:
            btn.setFixedHeight(main_button_height)
            btn.setMinimumWidth(160)  # 140에서 160으로 확대
        
        # 정보 버튼 크기 설정
        self.btn_version.setFixedHeight(info_button_height)
        self.btn_version.setFixedWidth(75)  # 80에서 75로 약간 축소
        
        # 이벤트 연결
        self.btn_load_left.clicked.connect(self.load_pdf_left)
        self.btn_load_right.clicked.connect(self.load_pdf_right)
        self.btn_compare.clicked.connect(self.compare_texts)
        self.btn_clear_highlights.clicked.connect(self.clear_all_highlights)
        self.btn_view_text.clicked.connect(self.view_comparison_text)
        self.btn_version.clicked.connect(self.show_version_info)
        
        # 버튼 스타일
        self.btn_compare.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        self.btn_view_text.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold; padding: 10px;")
        self.btn_version.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 5px; font-size: 11px;")
        
        # 버튼 배치
        top_button_layout.addWidget(self.btn_load_left)
        top_button_layout.addWidget(self.btn_load_right)
        top_button_layout.addWidget(self.btn_compare)
        top_button_layout.addWidget(self.btn_view_text)
        top_button_layout.addWidget(self.btn_clear_highlights)
        top_button_layout.addStretch()
        top_button_layout.addWidget(self.btn_version)
        
        self.main_layout.addLayout(top_button_layout)
        
        # PDF 뷰어 영역
        self.viewer_layout = QHBoxLayout()
        
        # 왼쪽
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        self.title_left = QLabel("PDF 1")
        self.title_left.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_left.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        left_layout.addWidget(self.title_left)
        
        self.viewer_left = PDFViewer()
        left_layout.addWidget(self.viewer_left)
        
        left_zoom_layout = QHBoxLayout()
        self.btn_zoom_in_left = QPushButton("🔍 확대")
        self.btn_zoom_out_left = QPushButton("🔍 축소")
        self.btn_clear_left = QPushButton("🗑️ 선택 해제")
        
        # 버튼 크기 통일
        for btn in [self.btn_zoom_in_left, self.btn_zoom_out_left, self.btn_clear_left]:
            btn.setFixedHeight(35)
        
        self.btn_zoom_in_left.clicked.connect(self.viewer_left.zoom_in)
        self.btn_zoom_out_left.clicked.connect(self.viewer_left.zoom_out)
        self.btn_clear_left.clicked.connect(self.viewer_left.clear_all_selections)
        left_zoom_layout.addWidget(self.btn_zoom_in_left)
        left_zoom_layout.addWidget(self.btn_zoom_out_left)
        left_zoom_layout.addWidget(self.btn_clear_left)
        left_layout.addLayout(left_zoom_layout)
        
        self.viewer_layout.addWidget(left_widget)
        
        # 오른쪽
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        self.title_right = QLabel("PDF 2")
        self.title_right.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_right.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        right_layout.addWidget(self.title_right)
        
        self.viewer_right = PDFViewer()
        right_layout.addWidget(self.viewer_right)
        
        right_zoom_layout = QHBoxLayout()
        self.btn_zoom_in_right = QPushButton("🔍 확대")
        self.btn_zoom_out_right = QPushButton("🔍 축소")
        self.btn_clear_right = QPushButton("🗑️ 선택 해제")
        
        # 버튼 크기 통일
        for btn in [self.btn_zoom_in_right, self.btn_zoom_out_right, self.btn_clear_right]:
            btn.setFixedHeight(35)
        
        self.btn_zoom_in_right.clicked.connect(self.viewer_right.zoom_in)
        self.btn_zoom_out_right.clicked.connect(self.viewer_right.zoom_out)
        self.btn_clear_right.clicked.connect(self.viewer_right.clear_all_selections)
        right_zoom_layout.addWidget(self.btn_zoom_in_right)
        right_zoom_layout.addWidget(self.btn_zoom_out_right)
        right_zoom_layout.addWidget(self.btn_clear_right)
        right_layout.addLayout(right_zoom_layout)
        
        self.viewer_layout.addWidget(right_widget)
        
        self.main_layout.addLayout(self.viewer_layout)
        
        # 결과 영역
        result_container = QWidget()
        result_layout = QVBoxLayout(result_container)
        result_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- 수정된 부분 (v1.4.0) ---
        # 비교 결과 타이틀 및 색상 설명
        title_widget = QWidget()
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(5, 5, 5, 5)
        title_layout.setSpacing(15)
        
        result_title = QLabel("📊 비교 결과")
        result_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        title_layout.addWidget(result_title)
        
        # 하이라이트 색상 설명
        color_legend = QLabel("🔴 삭제   🟢 추가   🟠 변경")
        color_legend.setStyleSheet("font-size: 12px; font-weight: bold; color: #555;")
        title_layout.addWidget(color_legend)
        
        title_layout.addStretch()
        
        # 주의 문구 추가
        warning_label = QLabel("⚠️ PDF의 특수기호, 숫자는 정확한 인식이 어려울 수 있습니다. 또한 **표(Table)**는 낱말(단어) 단위로 추출되는 과정에서 시각적 순서와 다를 수 있으므로, 셀(Cell) 단위로 비교하시는 것을 권장합니다.")
        warning_label.setStyleSheet("font-size: 11px; color: #D32F2F; font-weight: bold; margin-right: 10px;")
        title_layout.addWidget(warning_label)
        
        # 배경색을 흰색으로 변경, 하단 테두리 추가
        title_widget.setStyleSheet("background-color: #ffffff; border-bottom: 1px solid #ccc;")
        result_layout.addWidget(title_widget)
        # --- 수정 끝 ---
        
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(120)  # 200에서 120으로 축소
        self.result_text.setStyleSheet("background-color: #f9f9f9; padding: 8px; border: 1px solid #ccc; font-size: 12px;")
        
        features = ["단어 합치기", "재동기화 로직", "좌표 기준 정렬 (v1.3.0)", "한글 숫자 단위 변환", "불릿 포인트 제거 (30종)", "URL 제거", "구두점 제거", "공백 정규화", "대소문자 통일"]
        
        self.result_text.setHtml(f"""
        <p style='margin: 5px 0;'><b>📌 우체국금융개발원 디지털정보전략실 시스템품질팀 - PDF 텍스트 비교 도구 (v{VERSION})</b></p>
        <p style='margin: 3px 0; font-size: 11px;'><b>주요 기능:</b> {'  |  '.join(features)}</p>
        <p style='margin: 3px 0; font-size: 11px;'><b>사용 방법:</b> 양쪽 PDF에서 비교할 영역을 드래그 선택 후 '텍스트 비교' 클릭</p>
        """)
        result_layout.addWidget(self.result_text)
        
        result_container.setMaximumHeight(150)  # 220에서 150으로 축소
        self.main_layout.addWidget(result_container)
        
    def load_pdf_left(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "PDF 1 선택", "", "PDF Files (*.pdf)")
        if file_path:
            # 새 PDF를 로드하기 전에 기존 하이라이트 및 결과 초기화
            self.clear_all_highlights()
            success = self.viewer_left.load_pdf(file_path)
            if success:
                self.title_left.setText(f"PDF 1: {os.path.basename(file_path)}")
                print(f"✓ PDF 1 로드 완료: {file_path}")
            else:
                QMessageBox.critical(self, "오류", "PDF 1 로드 실패")
    
    def load_pdf_right(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "PDF 2 선택", "", "PDF Files (*.pdf)")
        if file_path:
            # 새 PDF를 로드하기 전에 기존 하이라이트 및 결과 초기화
            self.clear_all_highlights()
            success = self.viewer_right.load_pdf(file_path)
            if success:
                self.title_right.setText(f"PDF 2: {os.path.basename(file_path)}")
                print(f"✓ PDF 2 로드 완료: {file_path}")
            else:
                QMessageBox.critical(self, "오류", "PDF 2 로드 실패")
    

    def show_version_info(self):
        """버전 정보 표시"""
        dialog = VersionInfoDialog(self)
        dialog.exec()
    
    def view_comparison_text(self):
        """비교 텍스트 전문 보기 (텍스트 복사 기능 포함)"""
        try:
            # 선택 확인
            if not self.viewer_left.has_selection() and not self.viewer_right.has_selection():
                QMessageBox.warning(self, "경고", "양쪽 PDF 중 하나 이상에서 텍스트를 선택해주세요.")
                return
            
            # 텍스트 추출
            left_original = ""
            left_normalized = ""
            right_original = ""
            right_normalized = ""
            
            if self.viewer_left.has_selection():
                word_info_left = self.viewer_left.selected_word_info
                # 원본 텍스트 (정규화 전)
                left_original = ' '.join([w['text'] for w in word_info_left])
                # 정규화된 텍스트
                left_normalized = ' '.join([w['normalized'] for w in word_info_left])
            else:
                left_original = "선택된 텍스트 없음"
                left_normalized = "선택된 텍스트 없음"
            
            if self.viewer_right.has_selection():
                word_info_right = self.viewer_right.selected_word_info
                # 원본 텍스트 (정규화 전)
                right_original = ' '.join([w['text'] for w in word_info_right])
                # 정규화된 텍스트
                right_normalized = ' '.join([w['normalized'] for w in word_info_right])
            else:
                right_original = "선택된 텍스트 없음"
                right_normalized = "선택된 텍스트 없음"
            
            # 커스텀 다이얼로그 생성 (텍스트 복사 기능 포함)
            dialog = ViewComparisonTextDialog(
                left_original, 
                left_normalized, 
                right_original, 
                right_normalized, 
                self
            )
            dialog.exec()
            
        except Exception as e:
            print(f"❌ view_comparison_text 오류: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "오류", f"텍스트 보기 중 오류 발생:\n{e}")
    
    def compare_texts(self):
        """텍스트 비교 실행"""
        try:
            # 선택 확인
            if not self.viewer_left.has_selection():
                QMessageBox.warning(self, "경고", "왼쪽 PDF에서 텍스트를 선택해주세요.")
                return

            if not self.viewer_right.has_selection():
                QMessageBox.warning(self, "경고", "오른쪽 PDF에서 텍스트를 선택해주세요.")
                return

            print("\n" + "=" * 60)
            print(f"텍스트 비교 시작 (v{VERSION})")
            print("=" * 60)

            # 단어 정보 추출 (선택 영역 제거 전에 미리 추출)
            word_info_left = self.viewer_left.selected_word_info
            word_info_right = self.viewer_right.selected_word_info

            # 이전 비교 영역(옅은 파란색) 하이라이트 제거
            self.viewer_left.clear_selection_area_highlights()
            self.viewer_right.clear_selection_area_highlights()

            # 비교에 사용된 영역을 옅은 하이라이트로 표시하기 위한 bbox 계산 함수
            def highlight_compare_region(viewer, word_info):
                if not word_info:
                    return
                page_bbox_map = {}
                for w in word_info:
                    page = w['page']
                    x0, y0, x1, y1 = w['bbox']
                    if page not in page_bbox_map:
                        page_bbox_map[page] = [x0, y0, x1, y1]
                    else:
                        bx0, by0, bx1, by1 = page_bbox_map[page]
                        page_bbox_map[page] = [
                            min(bx0, x0),
                            min(by0, y0),
                            max(bx1, x1),
                            max(by1, y1),
                        ]
                # 아주 옅은 파란색으로 비교 영역 표시
                for page, bbox in page_bbox_map.items():
                    viewer.add_selection_area_highlight(
                        page,
                        bbox,
                        QColor(0, 120, 255, 30),  # alpha 30: 거의 보일랑 말랑
                        "compare-region"
                    )

            # 현재 비교 영역을 옅은 하이라이트로 표시
            highlight_compare_region(self.viewer_left, word_info_left)
            highlight_compare_region(self.viewer_right, word_info_right)

            # 선택 영역 초기화 (파란색 점선만 제거)
            # 선택 영역만 제거하고 selected_word_info와 하이라이트는 유지
            for lbl in self.viewer_left.page_labels:
                lbl.clear_selection()
            for lbl in self.viewer_right.page_labels:
                lbl.clear_selection()

            # 정규화된 단어 리스트
            words_left = [w['normalized'] for w in word_info_left]
            words_right = [w['normalized'] for w in word_info_right]
            
            print(f"\n[단어 분리]")
            print(f"왼쪽 단어 수: {len(words_left)}")
            print(f"오른쪽 단어 수: {len(words_right)}")
            
            # 재동기화 비교 (사용자 사전 포함)
            differences = compare_with_resync(words_left, words_right)
            
            # 유사도 계산
            matcher = SequenceMatcher(None, ' '.join(words_left), ' '.join(words_right))
            similarity = matcher.ratio() * 100
            
            print(f"\n유사도: {similarity:.2f}%")
            print(f"\n[비교 결과]")
            print(f"차이점 수: {len(differences)}")
            
            # 결과 HTML 생성
            result_html = f"""
            <p><b>✅ 비교 완료!</b></p>
            <p><b>정규화 적용:</b> 줄바꿈, 공백, 구두점, 불릿 포인트, 한글 숫자 단위 차이 무시</p>
            <p><b>유사도:</b> {similarity:.2f}%</p>
            <p><b>총 {len(differences)}개의 차이점 발견:</b></p>
            <ul style='max-height: 100px; overflow-y: auto;'>
            """
            
            # 차이점 표시
            for diff_type, left_idx, right_idx in differences:
                if diff_type == 'delete' and left_idx is not None:
                    word = word_info_left[left_idx]['text']
                    result_html += f"<li>❌ 삭제: '{word}'</li>"
                    # 하이라이트 추가 (빨간색)
                    self.viewer_left.add_word_highlight(
                        word_info_left[left_idx]['page'],
                        word_info_left[left_idx]['bbox'],
                        QColor(255, 0, 0, 100),
                        word
                    )
                elif diff_type == 'insert' and right_idx is not None:
                    word = word_info_right[right_idx]['text']
                    result_html += f"<li>✅ 추가: '{word}'</li>"
                    # 하이라이트 추가 (초록색)
                    self.viewer_right.add_word_highlight(
                        word_info_right[right_idx]['page'],
                        word_info_right[right_idx]['bbox'],
                        QColor(0, 255, 0, 100),
                        word
                    )
                elif diff_type == 'replace' and left_idx is not None and right_idx is not None:
                    word_left = word_info_left[left_idx]['text']
                    word_right = word_info_right[right_idx]['text']
                    result_html += f"<li>🔄 변경: '{word_left}' → '{word_right}'</li>"
                    # 하이라이트 추가 (주황색)
                    self.viewer_left.add_word_highlight(
                        word_info_left[left_idx]['page'],
                        word_info_left[left_idx]['bbox'],
                        QColor(255, 165, 0, 100),
                        word_left
                    )
                    self.viewer_right.add_word_highlight(
                        word_info_right[right_idx]['page'],
                        word_info_right[right_idx]['bbox'],
                        QColor(255, 165, 0, 100),
                        word_right
                    )
            
            result_html += "</ul>"
            result_html += "<p><i>💡 하이라이트는 선택 해제 후에도 유지됩니다. '하이라이트 지우기' 버튼으로 제거할 수 있습니다.</i></p>"
            
            self.result_text.setHtml(result_html)
            
            # 하이라이트 적용
            self.viewer_left.show_all_pages()
            self.viewer_right.show_all_pages()
            
            print("\n" + "=" * 60)
            print("텍스트 비교 완료")
            print("=" * 60 + "\n")
            
        except Exception as e:
            print(f"❌ compare_texts 오류: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "오류", f"텍스트 비교 중 오류 발생:\n{e}")
    
    def clear_all_highlights(self):
        """모든 하이라이트 제거"""
        try:
            self.viewer_left.clear_highlights()
            self.viewer_right.clear_highlights()
            
            features = ["단어 합치기", "재동기화 로직", "좌표 기준 정렬 (v1.3.0)", "한글 숫자 단위 변환", "불릿 포인트 제거 (30종)", "URL 제거", "구두점 제거", "공백 정규화", "대소문자 통일"]
        
            self.result_text.setHtml(f"""
            <p style='margin: 5px 0;'><b>📌 우체국금융개발원 디지털정보전략실 시스템품질팀 - PDF 텍스트 비교 도구 (v{VERSION})</b></p>
            <p style='margin: 3px 0; font-size: 11px;'><b>주요 기능:</b> {'  |  '.join(features)}</p>
            <p style='margin: 3px 0; font-size: 11px;'><b>사용 방법:</b> 양쪽 PDF에서 비교할 영역을 드래그 선택 후 '텍스트 비교' 클릭</p>
            """)
            
            print("✓ 하이라이트 제거")
        except Exception as e:
            print(f"❌ clear_all_highlights 오류: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())