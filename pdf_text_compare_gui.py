import sys
import fitz  # PyMuPDF
import re
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QScrollArea, QMessageBox
)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen
from PyQt6.QtCore import Qt, QRect, QPoint

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
        if event.button() == Qt.MouseButton.LeftButton:
            self.selection_start = event.pos()
            self.selection_end = event.pos()
            self.is_selecting = True
            self.update()
            
    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.selection_end = event.pos()
            self.update()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.is_selecting = False
            self.selection_end = event.pos()
            self.update()
            
            # 부모 PDFViewer에게 선택 완료 알림
            parent = self.parent()
            while parent and not isinstance(parent, PDFViewer):
                parent = parent.parent()
            if parent:
                parent.on_selection_complete(self.page_num, self.get_selection_rect())
                
    def paintEvent(self, event):
        super().paintEvent(event)
        
        # 선택 영역 그리기
        if self.selection_start and self.selection_end:
            painter = QPainter(self)
            
            # 반투명 노란색 배경
            color = QColor(255, 255, 0, 80)
            painter.setBrush(color)
            
            # 파란색 점선 테두리
            pen = QPen(QColor(0, 0, 255), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            
            # 선택 영역 사각형
            rect = QRect(self.selection_start, self.selection_end).normalized()
            painter.drawRect(rect)
            
            painter.end()
            
    def get_selection_rect(self):
        """선택 영역 반환"""
        if self.selection_start and self.selection_end:
            return QRect(self.selection_start, self.selection_end).normalized()
        return None
        
    def has_selection(self):
        """선택 영역이 있는지 확인"""
        return self.selection_start is not None and self.selection_end is not None
        
    def clear_selection(self):
        """선택 영역 초기화"""
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.update()


class PDFViewer(QScrollArea):
    """PDF 뷰어 위젯 - 스크롤 및 확대/축소 기능 포함"""
    
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
        self.page_images = []
        self.scale = 1.5  # 기본 확대 비율
        
        # 텍스트 선택 관련
        self.selected_text = ""
        self.selected_page = -1
        
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
            print(f"PDF 로드 오류: {e}")
            import traceback
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
        """모든 페이지 표시"""
        if not self.page_images:
            return
        for page_num, img in enumerate(self.page_images):
            self.page_labels[page_num].setPixmap(QPixmap.fromImage(img))
            self.page_labels[page_num].adjustSize()
            
    def zoom_in(self):
        """확대"""
        self.scale *= 1.2
        self.reload_pages()
        
    def zoom_out(self):
        """축소"""
        self.scale /= 1.2
        self.reload_pages()
        
    def reload_pages(self):
        """확대/축소 후 페이지 다시 로드"""
        if not self.pdf_doc:
            return
        
        # 선택 영역 초기화
        self.clear_all_selections()
        
        self.page_images.clear()
        for i in range(len(self.pdf_doc)):
            img = self.render_page_to_image(i)
            self.page_images.append(img)
        self.show_all_pages()
        
    def on_selection_complete(self, page_num, rect):
        """선택 완료 시 호출"""
        if rect and rect.width() > 5 and rect.height() > 5:  # 최소 크기 체크
            self.selected_page = page_num
            self.extract_selected_text(page_num, rect)
            print(f"✓ 선택 완료: 페이지 {page_num}, 영역 {rect}, 텍스트 길이: {len(self.selected_text)}")
        else:
            print(f"✗ 선택 영역이 너무 작습니다: {rect}")
                
    def extract_selected_text(self, page_num, rect):
        """선택한 영역에서 텍스트 추출"""
        if not self.pdf_doc:
            print("✗ PDF 문서가 로드되지 않았습니다")
            return
            
        try:
            # PDF 좌표계로 변환 (스케일 고려)
            x0 = rect.x() / self.scale
            y0 = rect.y() / self.scale
            x1 = (rect.x() + rect.width()) / self.scale
            y1 = (rect.y() + rect.height()) / self.scale
            
            print(f"PDF 좌표: ({x0:.1f}, {y0:.1f}, {x1:.1f}, {y1:.1f})")
            
            # 텍스트 추출
            page = self.pdf_doc.load_page(page_num)
            text = page.get_text("text", clip=(x0, y0, x1, y1))
            self.selected_text = text.strip()
            
            if self.selected_text:
                print(f"✓ 추출된 텍스트 (처음 100자): {self.selected_text[:100]}")
            else:
                print("✗ 텍스트가 추출되지 않았습니다. 영역에 텍스트가 없거나 이미지일 수 있습니다.")
                
        except Exception as e:
            print(f"✗ 텍스트 추출 오류: {e}")
            import traceback
            traceback.print_exc()
            self.selected_text = ""
        
    def get_selected_text(self):
        """선택된 텍스트 반환"""
        return self.selected_text
        
    def has_selection(self):
        """선택 영역이 있는지 확인"""
        # 모든 페이지 라벨을 확인하여 선택 영역이 있는지 체크
        for lbl in self.page_labels:
            if lbl.has_selection():
                return True
        return False
        
    def clear_all_selections(self):
        """모든 선택 영역 초기화"""
        for lbl in self.page_labels:
            lbl.clear_selection()
        self.selected_text = ""
        self.selected_page = -1
        print("선택 영역이 초기화되었습니다")


class MainWindow(QMainWindow):
    """메인 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF 텍스트 비교 도구")
        self.setGeometry(100, 100, 1600, 900)
        
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
        self.result_label = QLabel("📌 사용 방법:\n1. 양쪽 PDF를 로드하세요\n2. 각 PDF에서 비교할 텍스트를 마우스로 드래그하여 선택하세요\n3. '텍스트 비교' 버튼을 클릭하세요")
        self.result_label.setWordWrap(True)
        self.result_label.setMaximumHeight(120)
        self.result_label.setStyleSheet("background-color: #f0f0f0; padding: 10px; border: 1px solid #ccc;")
        self.main_layout.addWidget(self.result_label)
        
    def create_controls(self):
        """컨트롤 버튼 생성"""
        control_layout = QHBoxLayout()
        
        self.btn_load_left = QPushButton("📄 PDF 1 열기")
        self.btn_load_right = QPushButton("📄 PDF 2 열기")
        self.btn_compare = QPushButton("🔍 텍스트 비교")
        
        # 버튼 스타일
        button_style = "padding: 8px; font-size: 13px; font-weight: bold;"
        self.btn_load_left.setStyleSheet(button_style + "background-color: #e3f2fd;")
        self.btn_load_right.setStyleSheet(button_style + "background-color: #e3f2fd;")
        self.btn_compare.setStyleSheet(button_style + "background-color: #c8e6c9;")
        
        self.btn_load_left.clicked.connect(lambda: self.load_file('left'))
        self.btn_load_right.clicked.connect(lambda: self.load_file('right'))
        self.btn_compare.clicked.connect(self.compare_texts)
        
        control_layout.addWidget(self.btn_load_left)
        control_layout.addWidget(self.btn_load_right)
        control_layout.addWidget(self.btn_compare)
        
        self.main_layout.addLayout(control_layout)
        
    def load_file(self, viewer_id):
        """PDF 파일 로드"""
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
                
    def normalize_text(self, text):
        """텍스트 정규화 - 엔터와 공백 제거"""
        # 줄바꿈 제거
        text = text.replace('\n', '').replace('\r', '')
        # 연속된 공백을 하나로
        text = re.sub(r'\s+', ' ', text)
        # 앞뒤 공백 제거
        text = text.strip()
        return text
        
    def compare_texts(self):
        """선택한 텍스트 비교"""
        print("\n=== 텍스트 비교 시작 ===")
        
        # 선택 영역 확인
        has_left = self.viewer_left.has_selection()
        has_right = self.viewer_right.has_selection()
        
        print(f"왼쪽 선택 여부: {has_left}")
        print(f"오른쪽 선택 여부: {has_right}")
        
        text_left = self.viewer_left.get_selected_text()
        text_right = self.viewer_right.get_selected_text()
        
        print(f"왼쪽 텍스트 길이: {len(text_left)}")
        print(f"오른쪽 텍스트 길이: {len(text_right)}")
        
        if not text_left or not text_right:
            msg = "양쪽 PDF에서 텍스트를 선택해주세요.\n\n"
            if not has_left and not has_right:
                msg += "❌ 양쪽 모두 선택되지 않았습니다.\n"
            elif not has_left:
                msg += "❌ 왼쪽 PDF에서 텍스트를 선택하지 않았습니다.\n"
            elif not has_right:
                msg += "❌ 오른쪽 PDF에서 텍스트를 선택하지 않았습니다.\n"
            
            if has_left or has_right:
                msg += "\n💡 선택 영역은 보이지만 텍스트가 추출되지 않았습니다.\n"
                msg += "이미지로 된 PDF이거나 선택 영역에 텍스트가 없을 수 있습니다.\n"
                msg += "다른 영역을 선택해보거나 확대해서 다시 시도해보세요."
            else:
                msg += "\n💡 마우스로 드래그하여 텍스트 영역을 선택해주세요."
            
            QMessageBox.warning(self, "경고", msg)
            return
            
        # 텍스트 정규화
        normalized_left = self.normalize_text(text_left)
        normalized_right = self.normalize_text(text_right)
        
        print(f"정규화 후 왼쪽: {normalized_left[:50]}...")
        print(f"정규화 후 오른쪽: {normalized_right[:50]}...")
        
        # 단어 단위로 분리
        words_left = normalized_left.split()
        words_right = normalized_right.split()
        
        # 단어 레벨 비교
        differences = []
        max_len = max(len(words_left), len(words_right))
        
        for i in range(max_len):
            word_left = words_left[i] if i < len(words_left) else "[없음]"
            word_right = words_right[i] if i < len(words_right) else "[없음]"
            
            if word_left != word_right:
                differences.append(f"위치 {i+1}: '{word_left}' ≠ '{word_right}'")
        
        # 결과 표시
        if differences:
            result_text = f"✅ 비교 완료!\n총 {len(differences)}개의 차이점 발견:\n" + "\n".join(differences[:5])
            if len(differences) > 5:
                result_text += f"\n... 외 {len(differences) - 5}개 (상세 정보 확인)"
        else:
            result_text = "✅ 비교 완료!\n두 텍스트가 동일합니다."
            
        self.result_label.setText(result_text)
        
        # 상세 정보 다이얼로그
        detail_msg = f"=== PDF 1 선택 텍스트 ({len(text_left)}자) ===\n{text_left}\n\n"
        detail_msg += f"=== PDF 2 선택 텍스트 ({len(text_right)}자) ===\n{text_right}\n\n"
        detail_msg += f"=== 정규화 후 ===\nPDF 1 ({len(words_left)}단어): {normalized_left}\n\nPDF 2 ({len(words_right)}단어): {normalized_right}\n\n"
        detail_msg += f"=== 비교 결과 ===\n"
        if differences:
            detail_msg += "\n".join(differences)
        else:
            detail_msg += "차이점 없음 - 두 텍스트가 동일합니다."
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("텍스트 비교 결과")
        msg_box.setText(result_text)
        msg_box.setDetailedText(detail_msg)
        msg_box.exec()
        
        print("=== 텍스트 비교 완료 ===\n")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    
    print("=" * 60)
    print("PDF 텍스트 비교 도구 시작")
    print("=" * 60)
    print("사용 방법:")
    print("1. PDF 파일을 로드하세요")
    print("2. 마우스로 드래그하여 텍스트를 선택하세요")
    print("3. 선택 영역이 노란색으로 표시됩니다")
    print("4. 양쪽에서 선택 후 '텍스트 비교' 버튼을 클릭하세요")
    print("=" * 60)
    print()
    
    sys.exit(app.exec())
