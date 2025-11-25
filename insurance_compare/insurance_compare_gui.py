"""
가입설계서 비교 GUI 프로그램
"""
import sys
import os
import fitz  # PyMuPDF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QScrollArea, QSizePolicy, QMessageBox,
    QProgressBar, QToolTip, QCheckBox, QGroupBox
)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor
from PyQt6.QtCore import Qt, QRect, QThread, pyqtSignal, QEvent

# 로컬 모듈 임포트
from pdf_parser import InsurancePDFParser
from text_comparator import TextComparator


class ComparisonWorker(QThread):
    """비교 작업 워커 스레드"""
    finished = pyqtSignal(dict)
    progress = pyqtSignal(int)
    error = pyqtSignal(str)
    
    def __init__(self, pdf_path_a: str, pdf_path_b: str, compare_all: bool):
        super().__init__()
        self.pdf_path_a = pdf_path_a
        self.pdf_path_b = pdf_path_b
        self.compare_all = compare_all
    
    def run(self):
        try:
            self.progress.emit(10)
            
            # PDF 파싱
            parser_a = InsurancePDFParser(self.pdf_path_a)
            parser_a.parse()
            self.progress.emit(30)
            
            parser_b = InsurancePDFParser(self.pdf_path_b)
            parser_b.parse()
            self.progress.emit(50)
            
            # 텍스트 블록 추출
            blocks_a = parser_a.get_all_text_blocks()
            blocks_b = parser_b.get_all_text_blocks()
            self.progress.emit(60)
            
            # 비교
            comparator = TextComparator()
            results = comparator.compare_blocks(blocks_a, blocks_b)
            self.progress.emit(80)
            
            # 결과 패키징
            output = {
                'results': results,
                'blocks_a': blocks_a,
                'blocks_b': blocks_b,
                'parser_a': parser_a,
                'parser_b': parser_b,
                'diff_count': comparator.get_diff_count(results)
            }
            
            self.progress.emit(100)
            self.finished.emit(output)
            
        except Exception as e:
            self.error.emit(str(e))


class PDFViewer(QScrollArea):
    """PDF 뷰어 위젯"""
    
    PAGE_SPACING = 12
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 페이지 컨테이너
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.setSpacing(self.PAGE_SPACING)
        self.setWidget(self.container)
        
        self.pdf_doc = None
        self.page_images = []
        self.page_labels = []
        self.diff_data = {}
        self.scale = 2.0
    
    def clear_pages(self):
        """페이지 초기화"""
        for i in reversed(range(self.vbox.count())):
            w = self.vbox.itemAt(i).widget()
            if w:
                w.removeEventFilter(self)
                w.setParent(None)
        self.page_labels.clear()
        self.page_images.clear()
    
    def load_pdf(self, path: str) -> bool:
        """
        PDF 파일 로드
        
        Args:
            path: PDF 파일 경로
            
        Returns:
            성공 여부
        """
        try:
            self.clear_pages()
            self.pdf_doc = fitz.open(path)
            
            # 페이지별 렌더링
            for i in range(len(self.pdf_doc)):
                img = self.render_page_to_image(i)
                self.page_images.append(img)
                
                lbl = QLabel()
                lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                lbl.installEventFilter(self)
                self.vbox.addWidget(lbl)
                self.page_labels.append(lbl)
            
            self.show_all_pages()
            return True
        except Exception as e:
            print(f"PDF 로드 오류: {e}")
            self.pdf_doc = None
            self.clear_pages()
            return False
    
    def render_page_to_image(self, page_num: int) -> QImage:
        """
        페이지를 이미지로 렌더링
        
        Args:
            page_num: 페이지 번호
            
        Returns:
            QImage
        """
        page = self.pdf_doc.load_page(page_num)
        pix = page.get_pixmap(matrix=fitz.Matrix(self.scale, self.scale))
        fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
        return QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
    
    def draw_highlights_on(self, img: QImage, page_num: int) -> QImage:
        """
        이미지에 하이라이트 그리기
        
        Args:
            img: 원본 이미지
            page_num: 페이지 번호
            
        Returns:
            하이라이트가 그려진 이미지
        """
        if page_num not in self.diff_data:
            return img
        
        out = img.copy()
        painter = QPainter(out)
        
        for highlight in self.diff_data[page_num]:
            bbox = highlight['bbox']
            color_name = highlight['color']
            
            color = QColor(color_name)
            color.setAlpha(100)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            
            rect = QRect(
                int(bbox[0] * self.scale),
                int(bbox[1] * self.scale),
                int((bbox[2] - bbox[0]) * self.scale),
                int((bbox[3] - bbox[1]) * self.scale)
            )
            painter.drawRect(rect)
        
        painter.end()
        return out
    
    def show_all_pages(self):
        """모든 페이지 표시"""
        if not self.page_images:
            return
        
        for page_num, img in enumerate(self.page_images):
            highlighted = self.draw_highlights_on(img, page_num)
            self.page_labels[page_num].setPixmap(QPixmap.fromImage(highlighted))
            self.page_labels[page_num].adjustSize()
    
    def set_diff_data(self, diff_data: dict):
        """
        차이점 데이터 설정
        
        Args:
            diff_data: 페이지별 하이라이트 정보
        """
        self.diff_data = diff_data
        self.show_all_pages()
    
    def get_page_height(self, page_num: int) -> int:
        """페이지 높이 반환"""
        if 0 <= page_num < len(self.page_images):
            return self.page_images[page_num].height()
        return 0
    
    def get_page_start_y(self, page_num: int) -> int:
        """페이지 시작 Y좌표 반환"""
        total_height = sum(self.get_page_height(i) for i in range(page_num))
        total_spacing = page_num * self.PAGE_SPACING
        return total_height + total_spacing
    
    def eventFilter(self, source, event):
        """이벤트 필터 (툴팁 표시용)"""
        if isinstance(source, QLabel):
            try:
                page_num = self.page_labels.index(source)
            except ValueError:
                return super().eventFilter(source, event)
            
            if event.type() == QEvent.Type.MouseMove:
                pos = event.position().toPoint()
                self.show_diff_tooltip_on_page(page_num, pos, source)
            elif event.type() == QEvent.Type.Leave:
                QToolTip.hideText()
        
        return super().eventFilter(source, event)
    
    def show_diff_tooltip_on_page(self, page_num: int, pos, label):
        """차이점 툴팁 표시"""
        if not self.diff_data or page_num not in self.diff_data:
            return
        
        for highlight in self.diff_data[page_num]:
            bbox = highlight['bbox']
            rect = QRect(
                int(bbox[0] * self.scale),
                int(bbox[1] * self.scale),
                int((bbox[2] - bbox[0]) * self.scale),
                int((bbox[3] - bbox[1]) * self.scale)
            )
            
            if rect.contains(pos):
                QToolTip.showText(label.mapToGlobal(pos), highlight['detail'], label)
                return
        
        QToolTip.hideText()


class MainWindow(QMainWindow):
    """메인 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("가입설계서 비교 프로그램")
        self.setGeometry(100, 100, 1600, 900)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # 컨트롤 영역
        self._setup_controls()
        
        # 뷰어 영역
        self._setup_viewers()
        
        # 데이터
        self.pdf_path_a = None
        self.pdf_path_b = None
        self.blocks_a = []
        self.blocks_b = []
        self.comparison_results = None
        self.current_diff_index = -1
        self.diff_indices = []
        
        # 스크롤 동기화
        self.is_syncing = False
        self.viewer_a.verticalScrollBar().valueChanged.connect(
            lambda v: self.sync_scroll(self.viewer_a, self.viewer_b, v)
        )
        self.viewer_b.verticalScrollBar().valueChanged.connect(
            lambda v: self.sync_scroll(self.viewer_b, self.viewer_a, v)
        )
    
    def _setup_controls(self):
        """컨트롤 UI 설정"""
        control_layout = QHBoxLayout()
        
        # 파일 로드 버튼
        self.btn_load_a = QPushButton("템플릿 파일 열기 (원본)")
        self.btn_load_b = QPushButton("생성본 파일 열기")
        self.btn_load_a.clicked.connect(lambda: self.load_file('A'))
        self.btn_load_b.clicked.connect(lambda: self.load_file('B'))
        
        # 비교 옵션
        self.check_compare_all = QCheckBox("전체 비교")
        self.check_compare_all.setChecked(True)
        self.check_compare_all.setToolTip("체크 해제 시 섹션별 선택 비교 (현재는 전체 비교만 지원)")
        
        # 비교 시작 버튼
        self.btn_compare = QPushButton("비교 시작")
        self.btn_compare.clicked.connect(self.start_comparison)
        self.btn_compare.setStyleSheet("font-weight: bold; background-color: #4CAF50; color: white;")
        
        # 차이점 네비게이션
        self.btn_prev_diff = QPushButton("◀ 이전 차이점")
        self.btn_next_diff = QPushButton("다음 차이점 ▶")
        self.btn_prev_diff.clicked.connect(lambda: self.navigate_diff(-1))
        self.btn_next_diff.clicked.connect(lambda: self.navigate_diff(1))
        self.btn_prev_diff.setEnabled(False)
        self.btn_next_diff.setEnabled(False)
        
        # 레이아웃 구성
        control_layout.addWidget(self.btn_load_a)
        control_layout.addWidget(self.btn_load_b)
        control_layout.addWidget(self.check_compare_all)
        control_layout.addWidget(self.btn_compare)
        control_layout.addStretch()
        control_layout.addWidget(self.btn_prev_diff)
        control_layout.addWidget(self.btn_next_diff)
        
        self.main_layout.addLayout(control_layout)
        
        # 진행 바
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.main_layout.addWidget(self.progress_bar)
        
        # 상태 레이블
        self.status_label = QLabel("파일을 선택하고 비교를 시작하세요.")
        self.status_label.setStyleSheet("padding: 5px; background-color: #f0f0f0;")
        self.main_layout.addWidget(self.status_label)
    
    def _setup_viewers(self):
        """뷰어 UI 설정"""
        viewer_layout = QHBoxLayout()
        
        # 템플릿 뷰어
        viewer_a_widget = QWidget()
        viewer_a_layout = QVBoxLayout(viewer_a_widget)
        self.title_a = QLabel("템플릿 (원본)")
        self.title_a.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px; background-color: #e3f2fd;")
        self.viewer_a = PDFViewer()
        viewer_a_layout.addWidget(self.title_a)
        viewer_a_layout.addWidget(self.viewer_a)
        
        # 생성본 뷰어
        viewer_b_widget = QWidget()
        viewer_b_layout = QVBoxLayout(viewer_b_widget)
        self.title_b = QLabel("생성본")
        self.title_b.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px; background-color: #fff3e0;")
        self.viewer_b = PDFViewer()
        viewer_b_layout.addWidget(self.title_b)
        viewer_b_layout.addWidget(self.viewer_b)
        
        viewer_layout.addWidget(viewer_a_widget)
        viewer_layout.addWidget(viewer_b_widget)
        
        self.main_layout.addLayout(viewer_layout)
    
    def load_file(self, viewer_id: str):
        """
        파일 로드
        
        Args:
            viewer_id: 'A' 또는 'B'
        """
        caption = f"{'템플릿' if viewer_id == 'A' else '생성본'} PDF 파일 선택"
        path, _ = QFileDialog.getOpenFileName(self, caption, "", "PDF Files (*.pdf)")
        
        if path:
            viewer = self.viewer_a if viewer_id == 'A' else self.viewer_b
            
            if not viewer.load_pdf(path):
                QMessageBox.critical(self, "오류", "PDF 파일 로드에 실패했습니다.")
                return
            
            if viewer_id == 'A':
                self.pdf_path_a = path
                self.status_label.setText(f"템플릿 파일 로드됨: {os.path.basename(path)}")
            else:
                self.pdf_path_b = path
                self.status_label.setText(f"생성본 파일 로드됨: {os.path.basename(path)}")
    
    def start_comparison(self):
        """비교 시작"""
        if not self.pdf_path_a or not self.pdf_path_b:
            QMessageBox.warning(self, "경고", "두 PDF 파일을 모두 로드해야 합니다.")
            return
        
        # UI 비활성화
        self.btn_compare.setEnabled(False)
        self.btn_prev_diff.setEnabled(False)
        self.btn_next_diff.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText("비교 중...")
        
        # 워커 스레드 시작
        compare_all = self.check_compare_all.isChecked()
        self.worker = ComparisonWorker(self.pdf_path_a, self.pdf_path_b, compare_all)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.comparison_finished)
        self.worker.error.connect(self.comparison_error)
        self.worker.start()
    
    def comparison_finished(self, output: dict):
        """비교 완료"""
        self.comparison_results = output['results']
        self.blocks_a = output['blocks_a']
        self.blocks_b = output['blocks_b']
        diff_count = output['diff_count']
        
        # 하이라이트 적용
        self.viewer_a.set_diff_data(self.comparison_results['diff_highlights_a'])
        self.viewer_b.set_diff_data(self.comparison_results['diff_highlights_b'])
        
        # 차이점 인덱스 생성
        self.diff_indices = []
        for item in self.comparison_results['modified']:
            self.diff_indices.append(('modified', item['index_a'], item['index_b']))
        for item in self.comparison_results['deleted']:
            self.diff_indices.append(('deleted', item['index_a'], None))
        for item in self.comparison_results['added']:
            self.diff_indices.append(('added', None, item['index_b']))
        
        # UI 복원
        self.progress_bar.setVisible(False)
        self.btn_compare.setEnabled(True)
        
        if self.diff_indices:
            self.btn_prev_diff.setEnabled(True)
            self.btn_next_diff.setEnabled(True)
            self.current_diff_index = -1
            self.navigate_diff(1)
        
        # 결과 메시지
        msg = f"""비교 완료!

총 차이점: {diff_count['total']}개
- 변경됨: {diff_count['modified']}개
- 삭제됨: {diff_count['deleted']}개
- 추가됨: {diff_count['added']}개

색상 범례:
🟡 노란색: 변경된 내용
🔴 빨간색: 삭제된 내용
🟢 초록색: 추가된 내용

마우스를 올려 상세 정보를 확인하세요."""
        
        QMessageBox.information(self, "비교 완료", msg)
        self.status_label.setText(f"비교 완료 - 총 {diff_count['total']}개 차이점 발견")
    
    def comparison_error(self, error_msg: str):
        """비교 오류"""
        self.progress_bar.setVisible(False)
        self.btn_compare.setEnabled(True)
        QMessageBox.critical(self, "오류", f"비교 중 오류가 발생했습니다:\n{error_msg}")
        self.status_label.setText("비교 실패")
    
    def navigate_diff(self, direction: int):
        """
        차이점 네비게이션
        
        Args:
            direction: 1 (다음) 또는 -1 (이전)
        """
        if not self.diff_indices:
            return
        
        self.current_diff_index = (self.current_diff_index + direction) % len(self.diff_indices)
        diff_type, index_a, index_b = self.diff_indices[self.current_diff_index]
        
        # 스크롤 이동
        if diff_type == 'modified':
            block_a = self.blocks_a[index_a]
            scroll_y_a = self.get_scroll_from_block(self.viewer_a, block_a)
            self.viewer_a.verticalScrollBar().setValue(scroll_y_a)
        elif diff_type == 'deleted':
            block_a = self.blocks_a[index_a]
            scroll_y_a = self.get_scroll_from_block(self.viewer_a, block_a)
            self.viewer_a.verticalScrollBar().setValue(scroll_y_a)
        elif diff_type == 'added':
            block_b = self.blocks_b[index_b]
            scroll_y_b = self.get_scroll_from_block(self.viewer_b, block_b)
            self.viewer_b.verticalScrollBar().setValue(scroll_y_b)
        
        # 상태 업데이트
        self.status_label.setText(
            f"차이점 {self.current_diff_index + 1}/{len(self.diff_indices)} - {diff_type.upper()}"
        )
    
    def get_scroll_from_block(self, viewer: PDFViewer, block: dict) -> int:
        """블록 위치로부터 스크롤 값 계산"""
        scroll_y = viewer.get_page_start_y(block['page']) + (block['bbox'][1] * viewer.scale)
        return int(max(0, scroll_y - viewer.height() / 3))
    
    def sync_scroll(self, source_viewer: PDFViewer, target_viewer: PDFViewer, value: int):
        """스크롤 동기화"""
        if self.is_syncing or not self.comparison_results:
            return
        
        self.is_syncing = True
        
        # 매핑 정보
        sync_map = self.comparison_results['sync_map']
        source_blocks = self.blocks_a if source_viewer == self.viewer_a else self.blocks_b
        target_blocks = self.blocks_b if source_viewer == self.viewer_a else self.blocks_a
        
        if source_viewer == self.viewer_b:
            # B -> A 매핑으로 변환
            sync_map = {v: k for k, v in sync_map.items()}
        
        # 현재 스크롤 위치의 블록 찾기
        y_pos = value
        page_num = -1
        current_y = 0
        
        for i in range(len(source_viewer.page_images)):
            h = source_viewer.get_page_height(i) + source_viewer.PAGE_SPACING
            if y_pos < current_y + h:
                page_num = i
                break
            current_y += h
        
        if page_num == -1:
            self.is_syncing = False
            return
        
        # 해당 페이지의 블록 찾기
        block_idx = -1
        for i, block in enumerate(source_blocks):
            if block['page'] == page_num:
                block_top_y = source_viewer.get_page_start_y(page_num) + (block['bbox'][1] * source_viewer.scale)
                if block_top_y >= value:
                    block_idx = i
                    break
        
        # 매칭된 블록으로 스크롤
        if block_idx != -1:
            target_idx = sync_map.get(block_idx)
            if target_idx is not None:
                target_block = target_blocks[target_idx]
                target_scroll_y = self.get_scroll_from_block(target_viewer, target_block)
                target_viewer.verticalScrollBar().setValue(target_scroll_y)
        
        self.is_syncing = False


def main():
    """메인 함수"""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
