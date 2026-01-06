import sys
import fitz  # PyMuPDF
import re
import traceback
import os
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

# 버전 정보 및 배포 정보
VERSION = '1.1.7' 
RELEASE_DATE = os.environ.get('PDF_COMPARE_RELEASE_DATE', '2025-12-31')
DEVELOPER = '우체국금융개발원 디지털정보전략실 시스템품질팀'

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QScrollArea, QMessageBox, QTextEdit,
    QDialog, QFrame, QGraphicsOpacityEffect
)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QIcon, QFont
from PyQt6.QtCore import Qt, QRect, QTimer, QSize, QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup

# 하이라이트 색상 정의
COLOR_P1 = QColor(255, 255, 0, 140)   # 형광 노랑 (PDF1)
COLOR_P2 = QColor(0, 255, 127, 140)  # 형광 에메랄드 (PDF2)
COLOR_AREA = QColor(0, 120, 255, 15) # 최근 선택 영역
COLOR_MAIN_BLUE = "#004b93"
COLOR_COMPARE_BTN = "#FF6D00"        # 오렌지
COLOR_INFO_BTN = "#FFEB3B"           # 노란색

def get_resource_path(relative_path):
    """EXE 빌드 환경 리소스 경로 처리"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class ViewComparisonTextDialog(QDialog):
    """추출 데이터 확인 팝업"""
    def __init__(self, s1_norm, s2_norm, s1_raw, s2_raw, parent=None):
        super().__init__(parent)
        self.setWindowTitle("추출 데이터 정밀 확인")
        self.resize(1000, 850)
        main_layout = QVBoxLayout(self)

        def create_box_section(title, content_html, copy_data):
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 5, 0, 5)
            header = QHBoxLayout()
            header.addWidget(QLabel(f"<b>{title}</b>"))
            header.addStretch()
            btn = QPushButton("📋 텍스트 복사")
            btn.setFixedWidth(110); btn.clicked.connect(lambda: self.copy_to_clip(copy_data))
            header.addWidget(btn)
            text_edit = QTextEdit(); text_edit.setReadOnly(True)
            text_edit.setFont(QFont("Consolas", 10)); text_edit.setHtml(content_html)
            layout.addLayout(header); layout.addWidget(text_edit)
            return container

        norm_html = (f"<b>📄 PDF 1 (Normalized)</b><br><div style='background:#f2f2f2; padding:8px;'>{s1_norm}</div><br>"
                        f"<b>📄 PDF 2 (Normalized)</b><br><div style='background:#f2f2f2; padding:8px;'>{s2_norm}</div>")
        norm_copy = f"--- [PDF 1 Normalized] ---\n{s1_norm}\n\n--- [PDF 2 Normalized] ---\n{s2_norm}"
        main_layout.addWidget(create_box_section("[1] 정규화 텍스트 (실제 비교 대상)", norm_html, norm_copy), 1)

        raw_html = (f"<b>📄 PDF 1 (Raw)</b><br><div style='background:#f9f9f9; padding:8px;'>{s1_raw.replace('\n', '<br>')}</div><br>"
                       f"<b>📄 PDF 2 (Raw)</b><br><div style='background:#f9f9f9; padding:8px;'>{s2_raw.replace('\n', '<br>')}</div>")
        raw_copy = f"--- [PDF 1 Raw] ---\n{s1_raw}\n\n--- [PDF 2 Raw] ---\n{s2_raw}"
        main_layout.addWidget(create_box_section("[2] 원문 데이터 (띄어쓰기 및 줄바꿈 포함)", raw_html, raw_copy), 1)

        close_btn = QPushButton("닫기"); close_btn.setFixedWidth(100); close_btn.clicked.connect(self.accept)
        main_layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)

    def copy_to_clip(self, text):
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "성공", "텍스트가 클립보드에 복사되었습니다.")

class LoadingOverlay(QWidget):
    """역동적인 움직임과 보장된 가시성을 가진 대기 화면"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        
        self.layout = QVBoxLayout(self)
        self.bg_frame = QFrame()
        # 투명도를 낮추어(180) 뒷배경이 살짝만 비치게 함 (요청 반영)
        self.bg_frame.setStyleSheet("background-color: rgba(255, 255, 255, 200); border-radius: 40px; border: 1px solid #ddd;")
        self.bg_frame.setFixedSize(340, 240)
        
        f_layout = QVBoxLayout(self.bg_frame)
        self.icon_label = QLabel()
        logo_path = get_resource_path('posid_logo.png')
        if os.path.exists(logo_path):
            self.icon_label.setPixmap(QPixmap(logo_path).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.icon_label.setText("⚙️"); self.icon_label.setStyleSheet("font-size: 50px; color: #004b93;")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.msg = QLabel("처리 중..."); self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        
        f_layout.addStretch(); f_layout.addWidget(self.icon_label); f_layout.addWidget(self.msg); f_layout.addStretch()
        self.layout.addStretch(); self.layout.addWidget(self.bg_frame, 0, Qt.AlignmentFlag.AlignCenter); self.layout.addStretch()
        self.hide()

    def start_animation(self, message="처리 중..."):
        self.msg.setText(f"<b>{message}</b>")
        self.show()
        self.setGeometry(self.parent().rect())
        
        # 1. 가시성 확보 투명도 애니메이션 (30% ~ 0% 투명도 = Opacity 0.7 ~ 1.0)
        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(400)
        self.fade_anim.setStartValue(0.7)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # 2. 역동적인 이동 효과 (솟아오르기 + 플로팅)
        self.move_anim = QPropertyAnimation(self.bg_frame, b"pos")
        self.move_anim.setDuration(1000)
        center_pos = self.rect().center() - QPoint(self.bg_frame.width()//2, self.bg_frame.height()//2)
        self.move_anim.setStartValue(center_pos + QPoint(0, 40))
        self.move_anim.setKeyValueAt(0.2, center_pos - QPoint(0, 10)) # 탄성 효과
        self.move_anim.setKeyValueAt(0.6, center_pos + QPoint(0, 10))
        self.move_anim.setEndValue(center_pos)
        self.move_anim.setEasingCurve(QEasingCurve.Type.OutBack)

        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(self.fade_anim)
        self.anim_group.addAnimation(self.move_anim)
        self.anim_group.start()

    def stop_animation(self):
        if hasattr(self, 'anim_group'): self.anim_group.stop()
        self.hide(); self.opacity_effect.setOpacity(0.0)

class SelectableLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selection_start = None; self.selection_end = None
        self.is_selecting = False; self.page_num = -1
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selection_start = event.pos(); self.selection_end = event.pos()
            self.is_selecting = True; self.update()
            
    def mouseMoveEvent(self, event):
        if self.is_selecting: self.selection_end = event.pos(); self.update()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.is_selecting = False
            parent = self.parent()
            while parent and not isinstance(parent, PDFViewer): parent = parent.parent()
            if parent: parent.on_selection_complete(self.page_num, QRect(self.selection_start, self.selection_end).normalized())
            self.update()
                
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.selection_start and self.selection_end:
            painter = QPainter(self); painter.setBrush(QColor(0, 120, 255, 60))
            painter.setPen(QPen(QColor(0, 0, 255), 2, Qt.PenStyle.DashLine))
            painter.drawRect(QRect(self.selection_start, self.selection_end).normalized()); painter.end()

    def clear_selection(self):
        self.selection_start = None; self.selection_end = None; self.update()

class PDFViewer(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.container = QWidget(); self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(0, 0, 0, 0); self.setWidget(self.container)
        self.pdf_doc = None; self.page_labels = []; self.scale = 1.5
        self.char_data = []; self.raw_text = ""
        self.word_highlights = {}; self.last_compared_area = {}; self.pending_selection_rect = None

    def load_pdf(self, path):
        try: self.pdf_doc = fitz.open(path); self.reload_pages(); return True
        except: return False

    def reload_pages(self):
        if not self.pdf_doc: return
        for lbl in self.page_labels: lbl.setParent(None)
        self.page_labels.clear()
        for i in range(len(self.pdf_doc)):
            page = self.pdf_doc.load_page(i)
            pix = page.get_pixmap(matrix=fitz.Matrix(self.scale, self.scale))
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            lbl = SelectableLabel(self.container); lbl.page_num = i
            lbl.setPixmap(QPixmap.fromImage(img.copy()))
            self.vbox.addWidget(lbl); self.page_labels.append(lbl)
        self.refresh_highlights()

    def refresh_highlights(self):
        for i, lbl in enumerate(self.page_labels):
            img = lbl.pixmap().toImage()
            painter = QPainter(img)
            if i in self.last_compared_area:
                for bbox in self.last_compared_area[i]:
                    r = QRect(int(bbox[0]*self.scale), int(bbox[1]*self.scale), int((bbox[2]-bbox[0])*self.scale), int((bbox[3]-bbox[1])*self.scale))
                    painter.fillRect(r, COLOR_AREA)
            if i in self.word_highlights:
                for bbox, color in self.word_highlights[i]:
                    if bbox:
                        r = QRect(int(bbox[0]*self.scale), int(bbox[1]*self.scale), int((bbox[2]-bbox[0])*self.scale), int((bbox[3]-bbox[1])*self.scale))
                        painter.fillRect(r, color)
            painter.end(); lbl.setPixmap(QPixmap.fromImage(img))

    def on_selection_complete(self, page_num, rect):
        if rect.width() < 5: return
        x0, y0, x1, y1 = rect.x()/self.scale, rect.y()/self.scale, (rect.x()+rect.width())/self.scale, (rect.y()+rect.height())/self.scale
        self.pending_selection_rect = (page_num, fitz.Rect(x0, y0, x1, y1))
        self.char_data = []; self.raw_text = ""
        self.extract_and_process_text(page_num, rect)

    def extract_and_process_text(self, page_num, rect):
        """정밀 추출 엔진"""
        x0, y0, x1, y1 = rect.x()/self.scale, rect.y()/self.scale, (rect.x()+rect.width())/self.scale, (rect.y()+rect.height())/self.scale
        fitz_rect = fitz.Rect(x0, y0, x1, y1); page = self.pdf_doc.load_page(page_num); raw_dict = page.get_text("rawdict", clip=fitz_rect)
        all_raw_chars = []
        for block in raw_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    for char in span.get("chars", []):
                        c = char['c']
                        c_norm = unicodedata.normalize('NFC', c)
                        all_raw_chars.append({'char': c_norm, 'bbox': char['bbox'], 'y': char['bbox'][1], 'x': char['bbox'][0]})
        if not all_raw_chars: return
        all_raw_chars.sort(key=lambda x: x['y'])
        grouped = []
        if all_raw_chars:
            curr = [all_raw_chars[0]]
            for i in range(1, len(all_raw_chars)):
                if all_raw_chars[i]['y'] - curr[-1]['y'] < 5.0: curr.append(all_raw_chars[i])
                else: grouped.append(curr); curr = [all_raw_chars[i]]
            grouped.append(curr)
        final_norm = []; raw_lines = []; word_counter = 0
        for line in grouped:
            line.sort(key=lambda x: x['x']); line_str_raw = []; word_counter += 1
            for i, c in enumerate(line):
                line_str_raw.append(c['char'])
                if i > 0 and (line[i-1]['char'].strip() == "" or abs(c['x'] - line[i-1]['bbox'][2]) > 2.5): word_counter += 1
                clean_char = c['char'].lower().strip()
                if not re.match(r'[가-힣a-z0-9]', clean_char): continue
                if not final_norm or not (clean_char == final_norm[-1]['char'] and abs(c['x'] - final_norm[-1]['x']) < 2.5):
                    final_norm.append({'char': clean_char, 'bbox': c['bbox'], 'x': c['x'], 'page': page_num, 'word_id': word_counter})
            raw_lines.append("".join(line_str_raw))
        self.char_data = final_norm; self.raw_text = "\n".join(raw_lines)

    def zoom_in(self): self.scale *= 1.2; self.reload_pages()
    def zoom_out(self): self.scale /= 1.2; self.reload_pages()
    def clear_all_data(self):
        self.word_highlights.clear(); self.last_compared_area.clear(); self.char_data.clear(); self.raw_text = ""; self.pending_selection_rect = None
        for lbl in self.page_labels: lbl.clear_selection()
        self.reload_pages()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PDF 텍스트 비교 v{VERSION}")
        self.setGeometry(100, 100, 1600, 950)
        ico_path = get_resource_path('posid_logo.ico')
        if os.path.exists(ico_path): self.setWindowIcon(QIcon(ico_path))
        main_widget = QWidget(); self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget); layout.setSpacing(5)
        
        # --- 툴바 ---
        top_bar = QHBoxLayout()
        self.btn_load1 = QPushButton("📄 PDF 1 열기"); self.btn_load2 = QPushButton("📄 PDF 2 열기")
        btn_style = f"background:{COLOR_MAIN_BLUE}; color:white; font-weight:bold; height:36px; padding:0 15px; border-radius:4px;"
        self.btn_load1.setStyleSheet(btn_style); self.btn_load2.setStyleSheet(btn_style)
        top_bar.addWidget(self.btn_load1); top_bar.addWidget(self.btn_load2); top_bar.addStretch()
        self.btn_compare = QPushButton("🔍 비교 실행")
        self.btn_compare.setStyleSheet(f"background-color:{COLOR_COMPARE_BTN}; color:white; font-weight:bold; font-size:15px; height:42px; width:300px; border-radius:6px;")
        top_bar.addWidget(self.btn_compare); top_bar.addStretch()
        self.btn_view_text = QPushButton("📝 추출 데이터 확인"); self.btn_reset = QPushButton("비교결과초기화"); self.btn_info = QPushButton("i")
        self.btn_view_text.setStyleSheet(btn_style); self.btn_reset.setStyleSheet(btn_style)
        self.btn_info.setFixedSize(30, 36); self.btn_info.setStyleSheet(f"background:{COLOR_INFO_BTN}; border:1px solid #FBC02D; font-weight:bold; color:#5D4037; font-family:'Georgia'; font-size:18px; border-radius:4px;")
        top_bar.addWidget(self.btn_view_text); top_bar.addWidget(self.btn_reset); top_bar.addWidget(self.btn_info)
        layout.addLayout(top_bar)
        
        # --- 뷰어 ---
        view_area = QHBoxLayout()
        v1_box = QVBoxLayout(); v1_head = QHBoxLayout()
        self.btn_z1_p = QPushButton("확대 🔍+"); self.btn_z1_m = QPushButton("축소 🔍-")
        for b in [self.btn_z1_p, self.btn_z1_m]: b.setFixedSize(80, 24); b.setStyleSheet("font-size:11px; background:#f8f9fa; border:1px solid #ccc; border-radius:3px;")
        self.lbl_name1 = QLabel("<b>[PDF 1]</b>")
        v1_head.addWidget(self.btn_z1_p); v1_head.addWidget(self.btn_z1_m); v1_head.addWidget(self.lbl_name1); v1_head.addStretch()
        v1_box.addLayout(v1_head); self.viewer1 = PDFViewer(); v1_box.addWidget(self.viewer1); view_area.addLayout(v1_box)
        v2_box = QVBoxLayout(); v2_head = QHBoxLayout()
        self.btn_z2_p = QPushButton("확대 🔍+"); self.btn_z2_m = QPushButton("축소 🔍-")
        for b in [self.btn_z2_p, self.btn_z2_m]: b.setFixedSize(80, 24); b.setStyleSheet("font-size:11px; background:#f8f9fa; border:1px solid #ccc; border-radius:3px;")
        self.lbl_name2 = QLabel("<b>[PDF 2]</b>")
        v2_head.addWidget(self.btn_z2_p); v2_head.addWidget(self.btn_z2_m); v2_head.addWidget(self.lbl_name2); v2_head.addStretch()
        v2_box.addLayout(v2_head); self.viewer2 = PDFViewer(); v2_box.addWidget(self.viewer2); view_area.addLayout(v2_box)
        layout.addLayout(view_area)

        # --- 가이드 패널 ---
        guide_frame = QFrame(); guide_frame.setStyleSheet("background:#f9f9f9; border:1px solid #ddd; border-radius:6px;")
        g_layout = QHBoxLayout(guide_frame); g_layout.setContentsMargins(15, 10, 15, 10)
        
        # 범례 영역 수정 (요청 반영)
        legend_html = (
            f"<b>🎨 하이라이트 범례</b><br>"
            f"<span style='color:{COLOR_P1.name()}; background:{COLOR_P1.name()};'>■</span> PDF1 삭제/변경 (원본)  &nbsp;&nbsp;&nbsp; "
            f"<span style='color:{COLOR_P2.name()}; background:{COLOR_P2.name()};'>■</span> PDF2 추가/변경 (대상)<br>"
            f"<span style='font-size:10px; color:#555;'>※ 비교 엔진은 원본 문서에서 특정 문구가 사라지고(삭제), 대상 문서에 새로운 문구가<br>"
            f"들어온(추가) 것으로 분석하여 각각 매핑 표시합니다.</span>"
        )
        leg_label = QLabel(legend_html); leg_label.setStyleSheet("font-size:11px; line-height:1.6;"); g_layout.addWidget(leg_label, 1)
        
        caution_widget = QWidget(); caution_layout = QHBoxLayout(caution_widget); caution_layout.setContentsMargins(0,0,0,0)
        col1 = QLabel(
            "<b>⚠️ 주의</b><br>"
            "1. 본 프로그램은 <b style='color:red; font-family:Malgun Gothic;'>한글, 영문, 숫자</b>만을 정규화 대조합니다.<br>"
            "2. 모든 공백을 제거하고 분석하므로 <b style='color:red; font-family:Malgun Gothic;'>띄어쓰기 오류는 검증되지 않습니다.</b>"
        )
        col2 = QLabel(
            "<br>" 
            "3. 표(Table) 추출 시 셀 내용이 섞일 수 있으므로 반드시 <b style='color:red; font-family:Malgun Gothic;'>셀 단위 드래그</b>를 권장합니다.<br>"
            "4. 비교 결과는 <b style='color:red; font-family:Malgun Gothic;'>한쪽 문서에만 하이라이트</b>될 수 있습니다. 색칠된 부분의 반대쪽 문서 내용도 함께 확인하시기 바랍니다."
        )
        for c in [col1, col2]: c.setStyleSheet("font-size:11px; color:#444; line-height:1.6;"); caution_layout.addWidget(c)
        g_layout.addWidget(caution_widget, 3); layout.addWidget(guide_frame)

        self.loading = LoadingOverlay(self); self.last_s1_norm = ""; self.last_s2_norm = ""; self.last_s1_raw = ""; self.last_s2_raw = ""
        self.btn_load1.clicked.connect(self.load_p1); self.btn_load2.clicked.connect(self.load_p2)
        
        # 비교 실행 및 초기화 시 애니메이션 보장 로직
        self.btn_compare.clicked.connect(self.request_comparison)
        self.btn_reset.clicked.connect(self.request_reset)
        
        self.btn_view_text.clicked.connect(self.show_text_dialog); self.btn_info.clicked.connect(self.show_info)
        self.btn_z1_p.clicked.connect(self.viewer1.zoom_in); self.btn_z1_m.clicked.connect(self.viewer1.zoom_out)
        self.btn_z2_p.clicked.connect(self.viewer2.zoom_in); self.btn_z2_m.clicked.connect(self.viewer2.zoom_out)

    def request_comparison(self):
        if not self.viewer1.char_data or not self.viewer2.char_data:
            QMessageBox.warning(self, "경고", "양쪽 비교 영역을 먼저 드래그해주세요."); return
        self.loading.start_animation("비교 분석 중...")
        QApplication.processEvents() # UI 강제 업데이트로 애니메이션 즉시 노출
        QTimer.singleShot(100, self.run_comparison)

    def request_reset(self):
        self.loading.start_animation("비교결과 초기화 중...")
        QApplication.processEvents()
        QTimer.singleShot(1200, self.reset_all) # 충분한 확인을 위해 시간 연장

    def load_p1(self):
        path, _ = QFileDialog.getOpenFileName(self, "PDF 1 열기", "", "PDF (*.pdf)")
        if path:
            self.viewer1.clear_all_data()
            if self.viewer1.load_pdf(path): self.lbl_name1.setText(f"<b>[PDF 1] 📄 {os.path.basename(path)}</b>")
    def load_p2(self):
        path, _ = QFileDialog.getOpenFileName(self, "PDF 2 열기", "", "PDF (*.pdf)")
        if path:
            self.viewer2.clear_all_data()
            if self.viewer2.load_pdf(path): self.lbl_name2.setText(f"<b>[PDF 2] 📄 {os.path.basename(path)}</b>")

    def reset_all(self):
        try: self.viewer1.clear_all_data(); self.viewer2.clear_all_data(); self.last_s1_norm = ""; self.last_s2_norm = ""
        finally: self.loading.stop_animation()

    def run_comparison(self):
        try:
            self.viewer1.last_compared_area.clear(); self.viewer2.last_compared_area.clear()
            for v in [self.viewer1, self.viewer2]:
                if v.pending_selection_rect: p, r = v.pending_selection_rect; v.last_compared_area[p] = [r]
            self.last_s1_norm = "".join([d['char'] for d in self.viewer1.char_data])
            self.last_s2_norm = "".join([d['char'] for d in self.viewer2.char_data])
            self.last_s1_raw = self.viewer1.raw_text; self.last_s2_raw = self.viewer2.raw_text
            matcher = SequenceMatcher(None, self.last_s1_norm, self.last_s2_norm, autojunk=False)
            
            def highlight_entire_word(viewer, start_idx, end_idx, color):
                word_ids = set()
                for i in range(start_idx, end_idx): word_ids.add(viewer.char_data[i]['word_id'])
                for char in viewer.char_data:
                    if char['word_id'] in word_ids: self.add_hl(viewer, char, color)

            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == 'equal': continue
                if tag in ('delete', 'replace'): highlight_entire_word(self.viewer1, i1, i2, COLOR_P1)
                if tag in ('insert', 'replace'): highlight_entire_word(self.viewer2, j1, j2, COLOR_P2)
            for v in [self.viewer1, self.viewer2]:
                for lbl in v.page_labels: lbl.clear_selection()
                v.reload_pages()
        finally: self.loading.stop_animation()

    def show_info(self):
        d = QDialog(self); d.setWindowTitle("정보"); d.setFixedSize(420, 320)
        l = QVBoxLayout(d); l.setContentsMargins(30, 30, 30, 30)
        img_p = get_resource_path('posid_logo.png')
        if os.path.exists(img_p):
            img = QLabel(); img.setPixmap(QPixmap(img_p).scaled(200, 80, Qt.AspectRatioMode.KeepAspectRatio)); img.setAlignment(Qt.AlignmentFlag.AlignCenter); l.addWidget(img)
        t = QLabel(f"<div style='text-align:center;'><h2 style='color:#004b93;'>PDF 텍스트 비교</h2><b>버전:</b> {VERSION}<br><b>배포일:</b> {RELEASE_DATE}<br><br><b>제작:</b> {DEVELOPER}</div>"); l.addWidget(t)
        btn = QPushButton("확인"); btn.setFixedHeight(35); btn.clicked.connect(d.accept); l.addStretch(); l.addWidget(btn); d.exec()

    def show_text_dialog(self):
        if not self.last_s1_norm and not self.last_s2_norm: QMessageBox.information(self, "안내", "최근 비교 데이터가 없습니다."); return
        ViewComparisonTextDialog(self.last_s1_norm, self.last_s2_norm, self.last_s1_raw, self.last_s2_raw, self).exec()

    def add_hl(self, viewer, info, color):
        p = info['page']
        if p not in viewer.word_highlights: viewer.word_highlights[p] = []
        if not any(h[0] == info['bbox'] and h[1] == color for h in viewer.word_highlights[p]):
            viewer.word_highlights[p].append((info['bbox'], color))

    def resizeEvent(self, event):
        if self.loading.isVisible(): self.loading.setGeometry(self.rect())
        super().resizeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setFont(QFont("Malgun Gothic", 9))
    win = MainWindow(); win.show(); sys.exit(app.exec())