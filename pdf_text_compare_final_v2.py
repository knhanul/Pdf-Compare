import sys
import fitz  # PyMuPDF
import re
import traceback
from difflib import SequenceMatcher
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QScrollArea, QMessageBox, QTextEdit
)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen
from PyQt6.QtCore import Qt, QRect, QPoint

class SelectableLabel(QLabel):
    """텍스트 선택이 가능한 커스텀 라벨 - 선택 영역과 하이라이트 분리"""
    
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
            traceback.print_exc()
            
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
                
                # 부모 PDFViewer에게 선택 완료 알림
                parent = self.parent()
                while parent and not isinstance(parent, PDFViewer):
                    parent = parent.parent()
                if parent:
                    parent.on_selection_complete(self.page_num, self.get_selection_rect())
                
                # 선택 영역 표시 제거 (하이라이트는 PDFViewer가 관리)
                self.update()
        except Exception as e:
            print(f"❌ mouseReleaseEvent 오류: {e}")
            traceback.print_exc()
                
    def paintEvent(self, event):
        try:
            super().paintEvent(event)
            
            # 선택 중일 때만 선택 영역 표시 (파란색 점선)
            if self.is_selecting and self.selection_start and self.selection_end:
                painter = QPainter(self)
                
                # 반투명 파란색 배경
                color = QColor(0, 120, 255, 60)
                painter.setBrush(color)
                
                # 파란색 점선 테두리
                pen = QPen(QColor(0, 0, 255), 2, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                
                # 선택 영역 사각형
                rect = QRect(self.selection_start, self.selection_end).normalized()
                painter.drawRect(rect)
                
                painter.end()
        except Exception as e:
            print(f"❌ paintEvent 오류: {e}")
            
    def get_selection_rect(self):
        """선택 영역 반환"""
        if self.selection_start and self.selection_end:
            return QRect(self.selection_start, self.selection_end).normalized()
        return None
        
    def has_selection(self):
        """선택 영역이 있는지 확인"""
        return self.selection_start is not None and self.selection_end is not None
        
    def clear_selection(self):
        """선택 영역 초기화 (하이라이트는 유지)"""
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.update()


class PDFViewer(QScrollArea):
    """PDF 뷰어 위젯 - 하이라이트 영구 유지"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 페이지 표시용 컨테이너
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(10)
        self.setWidget(self.container)
        
        self.pdf_doc = None
        self.page_labels = []
        self.page_images = []  # 원본 이미지
        self.scale = 1.5  # 기본 확대 비율
        
        # 텍스트 선택 관련
        self.selected_text = ""
        self.selected_page = -1
        self.selected_word_info = []
        
        # 하이라이트 정보 저장 (영구 유지)
        self.word_highlights = {}  # {page_num: [(bbox, color, word), ...]}
        
    def clear_pages(self):
        """모든 페이지 라벨 제거"""
        for i in reversed(range(self.vbox.count())):
            w = self.vbox.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.page_labels.clear()
        self.page_images.clear()
        
    def load_pdf(self, path):
        """PDF 파일 로드"""
        try:
            self.clear_pages()
            self.pdf_doc = fitz.open(path)
            
            # 각 페이지를 이미지로 렌더링
            for i in range(len(self.pdf_doc)):
                img = self.render_page_to_image(i)
                self.page_images.append(img)
                
                # SelectableLabel 생성
                lbl = SelectableLabel(self.container)
                lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                lbl.page_num = i
                
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
        """페이지를 이미지로 렌더링"""
        page = self.pdf_doc.load_page(page_num)
        pix = page.get_pixmap(matrix=fitz.Matrix(self.scale, self.scale))
        fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
        return QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
        
    def show_all_pages(self):
        """모든 페이지 표시 (하이라이트 포함)"""
        try:
            for page_num in range(len(self.page_images)):
                if page_num < len(self.page_labels):
                    # 하이라이트가 있으면 적용, 없으면 원본
                    if page_num in self.word_highlights:
                        highlighted_img = self.draw_word_highlights(self.page_images[page_num], page_num)
                        self.page_labels[page_num].setPixmap(QPixmap.fromImage(highlighted_img))
                    else:
                        self.page_labels[page_num].setPixmap(QPixmap.fromImage(self.page_images[page_num]))
                    self.page_labels[page_num].adjustSize()
        except Exception as e:
            print(f"❌ show_all_pages 오류: {e}")
            traceback.print_exc()
            
    def zoom_in(self):
        """확대"""
        self.scale *= 1.2
        self.reload_pages()
        
    def zoom_out(self):
        """축소"""
        self.scale /= 1.2
        self.reload_pages()
        
    def reload_pages(self):
        """확대/축소 후 페이지 다시 로드 (하이라이트 유지)"""
        if not self.pdf_doc:
            return
        
        try:
            # 선택 영역만 초기화 (하이라이트는 유지)
            for lbl in self.page_labels:
                lbl.clear_selection()
            
            # 이미지 다시 렌더링
            self.page_images.clear()
            for i in range(len(self.pdf_doc)):
                img = self.render_page_to_image(i)
                self.page_images.append(img)
            
            # 하이라이트 다시 그리기
            self.show_all_pages()
            print("✓ 확대/축소 완료 (하이라이트 유지)")
            
        except Exception as e:
            print(f"❌ reload_pages 오류: {e}")
            traceback.print_exc()
        
    def on_selection_complete(self, page_num, rect):
        """선택 완료 시 호출"""
        try:
            if rect and rect.width() > 5 and rect.height() > 5:
                self.selected_page = page_num
                self.extract_text_with_word_info(page_num, rect)
                print(f"✓ 선택 완료: 페이지 {page_num}, 단어 수: {len(self.selected_word_info)}")
            else:
                print(f"✗ 선택 영역이 너무 작습니다")
        except Exception as e:
            print(f"❌ on_selection_complete 오류: {e}")
            traceback.print_exc()
    
    def extract_text_with_word_info(self, page_num, rect):
        """선택 영역에서 텍스트와 단어 정보 추출"""
        if not self.pdf_doc:
            return
        
        try:
            # PDF 좌표계로 변환
            x0 = rect.x() / self.scale
            y0 = rect.y() / self.scale
            x1 = (rect.x() + rect.width()) / self.scale
            y1 = (rect.y() + rect.height()) / self.scale
            
            selection_rect = fitz.Rect(x0, y0, x1, y1)
            page = self.pdf_doc.load_page(page_num)
            
            # 단어 단위로 텍스트 추출
            words = page.get_text("words")
            
            self.selected_word_info = []
            text_parts = []
            current_sentence = []
            
            for word_tuple in words:
                word_bbox = fitz.Rect(word_tuple[:4])
                word_text = word_tuple[4]
                
                # 선택 영역과 겹치는지 확인
                if selection_rect.intersects(word_bbox):
                    self.selected_word_info.append({
                        'text': word_text,
                        'bbox': word_tuple[:4],
                        'page': page_num
                    })
                    current_sentence.append(word_text)
                    
                    # 마침표로 끝나면 문장 완료
                    if word_text.endswith('.') or word_text.endswith('。'):
                        text_parts.append(' '.join(current_sentence))
                        current_sentence = []
            
            # 마지막 문장 처리
            if current_sentence:
                text_parts.append(' '.join(current_sentence))
            
            self.selected_text = ' '.join(text_parts)
            print(f"✓ 추출된 단어 수: {len(self.selected_word_info)}")
            
        except Exception as e:
            print(f"❌ 텍스트 추출 오류: {e}")
            traceback.print_exc()
            self.selected_text = ""
            self.selected_word_info = []
    
    def get_selected_text(self):
        return self.selected_text
    
    def get_selected_word_info(self):
        return self.selected_word_info
    
    def has_selection(self):
        for lbl in self.page_labels:
            if lbl.has_selection():
                return True
        return False
    
    def clear_all_selections(self):
        """선택 영역만 초기화 (하이라이트는 유지)"""
        for lbl in self.page_labels:
            lbl.clear_selection()
        print("✓ 선택 영역 초기화 (하이라이트는 유지)")
    
    def highlight_word_differences(self, word_diffs):
        """단어 단위로 차이점 하이라이트 (영구 유지)"""
        try:
            print(f"하이라이트 시작: {len(word_diffs)}개 단어")
            
            # 기존 하이라이트에 추가 (덮어쓰지 않음)
            for i, diff in enumerate(word_diffs):
                try:
                    page_num = diff['page']
                    bbox = diff['bbox']
                    diff_type = diff['type']
                    
                    # 색상 결정
                    if diff_type == 'add':
                        color = QColor(0, 255, 0, 120)  # 초록색
                    elif diff_type == 'delete':
                        color = QColor(255, 0, 0, 120)  # 빨간색
                    else:  # change
                        color = QColor(255, 200, 0, 120)  # 주황색
                    
                    if page_num not in self.word_highlights:
                        self.word_highlights[page_num] = []
                    
                    self.word_highlights[page_num].append((bbox, color, diff['word']))
                    
                except Exception as e:
                    print(f"❌ 단어 {i} 하이라이트 오류: {e}")
                    continue
            
            # 하이라이트 다시 그리기
            self.show_all_pages()
            print(f"✓ 하이라이트 완료: {len(self.word_highlights)}개 페이지")
            
        except Exception as e:
            print(f"❌ highlight_word_differences 오류: {e}")
            traceback.print_exc()
    
    def draw_word_highlights(self, img, page_num):
        """이미지에 단어 하이라이트 그리기"""
        try:
            if page_num not in self.word_highlights:
                return img
            
            highlighted = img.copy()
            painter = QPainter(highlighted)
            
            for bbox, color, word in self.word_highlights[page_num]:
                try:
                    painter.setBrush(color)
                    painter.setPen(Qt.PenStyle.NoPen)
                    
                    rect = QRect(
                        int(bbox[0] * self.scale),
                        int(bbox[1] * self.scale),
                        int((bbox[2] - bbox[0]) * self.scale),
                        int((bbox[3] - bbox[1]) * self.scale)
                    )
                    painter.drawRect(rect)
                except Exception as e:
                    print(f"❌ 단어 '{word}' 그리기 오류: {e}")
                    continue
            
            painter.end()
            return highlighted
            
        except Exception as e:
            print(f"❌ draw_word_highlights 오류: {e}")
            traceback.print_exc()
            return img
    
    def clear_highlights(self):
        """모든 하이라이트 제거"""
        self.word_highlights.clear()
        self.show_all_pages()
        print("✓ 모든 하이라이트 제거")


class MainWindow(QMainWindow):
    """메인 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF 텍스트 비교 도구 (하이라이트 영구 유지)")
        self.setGeometry(100, 100, 1600, 1000)
        
        # 중앙 위젯
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # 컨트롤 버튼
        self.create_controls()
        
        # PDF 뷰어 (좌우 배치)
        self.viewer_layout = QHBoxLayout()
        
        # 왼쪽 뷰어
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        self.title_left = QLabel("PDF 1")
        self.title_left.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_left.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        left_layout.addWidget(self.title_left)
        
        self.viewer_left = PDFViewer()
        left_layout.addWidget(self.viewer_left)
        
        # 왼쪽 확대/축소 버튼
        left_zoom_layout = QHBoxLayout()
        self.btn_zoom_in_left = QPushButton("확대 (+)")
        self.btn_zoom_out_left = QPushButton("축소 (-)")
        self.btn_clear_left = QPushButton("선택 해제")
        self.btn_zoom_in_left.clicked.connect(self.viewer_left.zoom_in)
        self.btn_zoom_out_left.clicked.connect(self.viewer_left.zoom_out)
        self.btn_clear_left.clicked.connect(self.viewer_left.clear_all_selections)
        left_zoom_layout.addWidget(self.btn_zoom_in_left)
        left_zoom_layout.addWidget(self.btn_zoom_out_left)
        left_zoom_layout.addWidget(self.btn_clear_left)
        left_layout.addLayout(left_zoom_layout)
        
        self.viewer_layout.addWidget(left_widget)
        
        # 오른쪽 뷰어
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        self.title_right = QLabel("PDF 2")
        self.title_right.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_right.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        right_layout.addWidget(self.title_right)
        
        self.viewer_right = PDFViewer()
        right_layout.addWidget(self.viewer_right)
        
        # 오른쪽 확대/축소 버튼
        right_zoom_layout = QHBoxLayout()
        self.btn_zoom_in_right = QPushButton("확대 (+)")
        self.btn_zoom_out_right = QPushButton("축소 (-)")
        self.btn_clear_right = QPushButton("선택 해제")
        self.btn_zoom_in_right.clicked.connect(self.viewer_right.zoom_in)
        self.btn_zoom_out_right.clicked.connect(self.viewer_right.zoom_out)
        self.btn_clear_right.clicked.connect(self.viewer_right.clear_all_selections)
        right_zoom_layout.addWidget(self.btn_zoom_in_right)
        right_zoom_layout.addWidget(self.btn_zoom_out_right)
        right_zoom_layout.addWidget(self.btn_clear_right)
        right_layout.addLayout(right_zoom_layout)
        
        self.viewer_layout.addWidget(right_widget)
        
        self.main_layout.addLayout(self.viewer_layout)
        
        # 결과 표시 영역
        result_container = QWidget()
        result_layout = QVBoxLayout(result_container)
        result_layout.setContentsMargins(0, 0, 0, 0)
        
        result_title = QLabel("📊 비교 결과")
        result_title.setStyleSheet("font-weight: bold; font-size: 13px; padding: 5px; background-color: #e0e0e0;")
        result_layout.addWidget(result_title)
        
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(200)
        self.result_text.setStyleSheet("background-color: #f9f9f9; padding: 10px; border: 1px solid #ccc;")
        self.result_text.setHtml("""
        <p><b>📌 사용 방법:</b></p>
        <ol>
        <li>양쪽 PDF를 로드하세요</li>
        <li>각 PDF에서 비교할 텍스트를 마우스로 드래그하여 선택하세요</li>
        <li>'🔍 텍스트 비교' 버튼을 클릭하세요</li>
        <li>선택을 해제해도 하이라이트는 계속 유지됩니다</li>
        </ol>
        <p><b>색상 의미:</b> <span style='background-color: #ffcccc;'>빨간색=삭제</span> <span style='background-color: #ccffcc;'>초록색=추가</span> <span style='background-color: #ffeecc;'>주황색=변경</span></p>
        """)
        result_layout.addWidget(self.result_text)
        
        result_container.setMaximumHeight(220)
        self.main_layout.addWidget(result_container)
        
    def create_controls(self):
        """컨트롤 버튼 생성"""
        control_layout = QHBoxLayout()
        
        self.btn_load_left = QPushButton("📄 PDF 1 열기")
        self.btn_load_right = QPushButton("📄 PDF 2 열기")
        self.btn_compare = QPushButton("🔍 텍스트 비교")
        self.btn_clear_highlights = QPushButton("🧹 하이라이트 지우기")
        
        button_style = "padding: 8px; font-size: 13px; font-weight: bold;"
        self.btn_load_left.setStyleSheet(button_style + "background-color: #e3f2fd;")
        self.btn_load_right.setStyleSheet(button_style + "background-color: #e3f2fd;")
        self.btn_compare.setStyleSheet(button_style + "background-color: #c8e6c9;")
        self.btn_clear_highlights.setStyleSheet(button_style + "background-color: #ffebee;")
        
        self.btn_load_left.clicked.connect(lambda: self.load_file('left'))
        self.btn_load_right.clicked.connect(lambda: self.load_file('right'))
        self.btn_compare.clicked.connect(self.compare_texts)
        self.btn_clear_highlights.clicked.connect(self.clear_all_highlights)
        
        control_layout.addWidget(self.btn_load_left)
        control_layout.addWidget(self.btn_load_right)
        control_layout.addWidget(self.btn_compare)
        control_layout.addWidget(self.btn_clear_highlights)
        
        self.main_layout.addLayout(control_layout)
    
    def load_file(self, viewer_id):
        """PDF 파일 로드"""
        try:
            caption = f"PDF {1 if viewer_id == 'left' else 2} 파일 선택"
            path, _ = QFileDialog.getOpenFileName(self, caption, "", "PDF Files (*.pdf)")
            
            if path:
                viewer = self.viewer_left if viewer_id == 'left' else self.viewer_right
                if not viewer.load_pdf(path):
                    QMessageBox.critical(self, "오류", "PDF 파일 로드에 실패했습니다.")
                else:
                    title = self.title_left if viewer_id == 'left' else self.title_right
                    filename = path.split('/')[-1]
                    title.setText(f"PDF {1 if viewer_id == 'left' else 2}: {filename}")
                    print(f"✓ PDF 로드 완료: {filename}")
        except Exception as e:
            print(f"❌ load_file 오류: {e}")
            traceback.print_exc()
    
    def normalize_text(self, text):
        """텍스트 정규화"""
        text = text.replace('\n', '').replace('\r', '')
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        return text
    
    def compare_texts(self):
        """선택한 텍스트 비교"""
        try:
            print("\n" + "="*60)
            print("텍스트 비교 시작")
            print("="*60)
            
            text_left = self.viewer_left.get_selected_text()
            text_right = self.viewer_right.get_selected_text()
            
            if not text_left or not text_right:
                QMessageBox.warning(self, "경고", "양쪽 PDF에서 텍스트를 선택해주세요.")
                return
            
            # 텍스트 정규화
            normalized_left = self.normalize_text(text_left)
            normalized_right = self.normalize_text(text_right)
            
            # 단어 단위로 분리
            words_left = normalized_left.split()
            words_right = normalized_right.split()
            
            print(f"왼쪽 단어 수: {len(words_left)}")
            print(f"오른쪽 단어 수: {len(words_right)}")
            
            # 단어 정보 가져오기
            word_info_left = self.viewer_left.get_selected_word_info()
            word_info_right = self.viewer_right.get_selected_word_info()
            
            # SequenceMatcher로 비교
            matcher = SequenceMatcher(None, words_left, words_right)
            
            differences = []
            left_diffs = []
            right_diffs = []
            
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == 'delete':
                    for i in range(i1, i2):
                        differences.append(f"❌ 삭제: '{words_left[i]}'")
                        if i < len(word_info_left):
                            left_diffs.append({
                                'word': words_left[i],
                                'type': 'delete',
                                'bbox': word_info_left[i]['bbox'],
                                'page': word_info_left[i]['page']
                            })
                elif tag == 'insert':
                    for j in range(j1, j2):
                        differences.append(f"✅ 추가: '{words_right[j]}'")
                        if j < len(word_info_right):
                            right_diffs.append({
                                'word': words_right[j],
                                'type': 'add',
                                'bbox': word_info_right[j]['bbox'],
                                'page': word_info_right[j]['page']
                            })
                elif tag == 'replace':
                    for i in range(i1, i2):
                        if i < len(word_info_left):
                            differences.append(f"🔄 변경: '{words_left[i]}' → '...'")
                            left_diffs.append({
                                'word': words_left[i],
                                'type': 'change',
                                'bbox': word_info_left[i]['bbox'],
                                'page': word_info_left[i]['page']
                            })
                    for j in range(j1, j2):
                        if j < len(word_info_right):
                            right_diffs.append({
                                'word': words_right[j],
                                'type': 'change',
                                'bbox': word_info_right[j]['bbox'],
                                'page': word_info_right[j]['page']
                            })
            
            print(f"차이점 수: {len(differences)}")
            
            # 결과 표시
            result_html = "<h3>✅ 비교 완료!</h3>"
            
            if differences:
                result_html += f"<p><b>총 {len(differences)}개의 차이점 발견:</b></p><ul>"
                for diff in differences[:20]:
                    if '삭제' in diff:
                        result_html += f"<li style='color: red;'>{diff}</li>"
                    elif '추가' in diff:
                        result_html += f"<li style='color: green;'>{diff}</li>"
                    else:
                        result_html += f"<li style='color: orange;'>{diff}</li>"
                result_html += "</ul>"
                
                if len(differences) > 20:
                    result_html += f"<p><i>... 외 {len(differences) - 20}개</i></p>"
                
                result_html += "<p><b>💡 선택을 해제해도 하이라이트는 계속 유지됩니다!</b></p>"
            else:
                result_html += "<p><b>두 텍스트가 동일합니다.</b></p>"
            
            self.result_text.setHtml(result_html)
            
            # 하이라이트 적용
            print("하이라이트 적용 중...")
            self.viewer_left.highlight_word_differences(left_diffs)
            self.viewer_right.highlight_word_differences(right_diffs)
            
            # 선택 영역 해제 (하이라이트는 유지)
            self.viewer_left.clear_all_selections()
            self.viewer_right.clear_all_selections()
            
            print("="*60)
            print("텍스트 비교 완료 - 하이라이트 영구 유지")
            print("="*60 + "\n")
            
        except Exception as e:
            print(f"❌ compare_texts 오류: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, "오류", f"비교 중 오류가 발생했습니다:\n{str(e)}")
    
    def clear_all_highlights(self):
        """모든 하이라이트 지우기"""
        try:
            self.viewer_left.clear_highlights()
            self.viewer_right.clear_highlights()
            
            self.result_text.setHtml("""
            <p><b>📌 사용 방법:</b></p>
            <ol>
            <li>양쪽 PDF를 로드하세요</li>
            <li>각 PDF에서 비교할 텍스트를 마우스로 드래그하여 선택하세요</li>
            <li>'🔍 텍스트 비교' 버튼을 클릭하세요</li>
            <li>선택을 해제해도 하이라이트는 계속 유지됩니다</li>
            </ol>
            """)
            
            print("✓ 모든 하이라이트가 지워졌습니다")
        except Exception as e:
            print(f"❌ clear_all_highlights 오류: {e}")
            traceback.print_exc()


if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        main_window = MainWindow()
        main_window.show()
        
        print("=" * 60)
        print("PDF 텍스트 비교 도구 (하이라이트 영구 유지 버전)")
        print("=" * 60)
        print("기능:")
        print("- 선택 해제 후에도 하이라이트 계속 유지")
        print("- 확대/축소해도 하이라이트 유지")
        print("- 스크롤해도 하이라이트 유지")
        print("- '하이라이트 지우기' 버튼으로만 제거 가능")
        print("=" * 60)
        print()
        
        sys.exit(app.exec())
    except Exception as e:
        print(f"❌ 프로그램 시작 오류: {e}")
        traceback.print_exc()
