import sys
import fitz  # PyMuPDF
import re
import traceback
import os
from datetime import datetime
from difflib import SequenceMatcher

# Get version and date from environment variables (set by build script)
VERSION = os.environ.get('PDF_COMPARE_VERSION', '1.1.4') 
RELEASE_DATE = os.environ.get('PDF_COMPARE_RELEASE_DATE', '2026-01-05')
DEVELOPER = '우체국금융개발원 디지털정보전략실 시스템품질팀'

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QScrollArea, QMessageBox, QTextEdit,
    QDialog, QFrame, QGraphicsOpacityEffect
)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QIcon, QFont
from PyQt6.QtCore import Qt, QRect, QTimer, QSize, QPropertyAnimation, QEasingCurve

# Highlight colors
COLOR_P1 = QColor(255, 255, 0, 120)   # Fluorescent Yellow
COLOR_P2 = QColor(0, 255, 127, 130)  # Fluorescent Emerald
COLOR_AREA = QColor(0, 120, 255, 15) # Recent Selection
COLOR_MAIN_BLUE = "#004b93"
COLOR_COMPARE_BTN = "#FF6D00"        # Compare Action
COLOR_INFO_BTN = "#FFEB3B"           # Info Button

def get_resource_path(relative_path):
    """Get absolute path to resource for PyInstaller and Development"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)



# ===== Diff helper (v1.1.4+) =====
# Why: character-by-character diff can "steal" digits/letters from other places in the selection
#      (e.g., a phone number's "2" or "21" gets matched to "24021" elsewhere). To prevent this,
#      we diff by *tokens* (digit-run / alpha-run / hangul-run) and add structural boundary tokens
#      for line breaks and large horizontal gaps.
DEBUG_DIFF = os.environ.get("PDF_COMPARE_DEBUG", "0").lower() in ("1", "true", "yes", "y")

TOKEN_NL = "\n"   # line boundary (not highlighted)
TOKEN_GAP = "\t"  # large horizontal gap boundary (not highlighted)

def _char_category(ch):
    """Return a coarse category used for tokenization."""
    if not ch:
        return ""
    if ch.isdigit():
        return "D"
    c = ch.lower()
    if "a" <= c <= "z":
        return "A"
    # Hangul syllables + jamo
    if ("가" <= ch <= "힣") or ("ㄱ" <= ch <= "ㅎ") or ("ㅏ" <= ch <= "ㅣ"):
        return "H"
    return ""

def _median(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    values = sorted(values)
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0

def build_token_stream(char_data, y_threshold=5.0, x_gap_threshold=None):
    """
    Convert char_data (list of {'char','bbox','page'}) into:
      - tokens: list[str]                         (token stream for SequenceMatcher)
      - token_to_char_idxs: list[list[int]|None]  (token -> original char_data indices)
      - pretty_text: str                          (for '추출 데이터 확인' window)

    Tokens are contiguous runs of the same category:
      - digits (e.g. 01092562100)
      - latin letters (lowercased at extraction)
      - hangul/jamo

    Additionally, we insert boundary tokens:
      - TOKEN_NL for line breaks (based on bbox y)
      - TOKEN_GAP for large horizontal gaps (based on bbox x)
    Boundary tokens are NOT highlighted (mapping is None).
    """
    if not char_data:
        return [], [], ""

    # Auto-tune gap threshold from median character width if not provided
    if x_gap_threshold is None:
        widths = []
        for d in char_data:
            try:
                b = d["bbox"]
                widths.append(max(0.0, float(b[2]) - float(b[0])))
            except Exception:
                continue
        med_w = _median(widths) or 0.0
        x_gap_threshold = max(6.0, med_w * 2.2)

    tokens = []
    token_to_char_idxs = []
    pretty_parts = []

    curr_chars = []
    curr_idxs = []
    curr_cat = None

    prev_y0 = None
    prev_x1 = None

    def flush():
        nonlocal curr_cat
        if curr_chars:
            tokens.append("".join(curr_chars))
            token_to_char_idxs.append(curr_idxs[:])
            curr_chars.clear()
            curr_idxs.clear()
        curr_cat = None

    for idx, item in enumerate(char_data):
        ch = item.get("char", "")
        cat = _char_category(ch)
        if not cat:
            continue

        try:
            x0, y0, x1, _y1 = item["bbox"]
            x0 = float(x0); y0 = float(y0); x1 = float(x1)
        except Exception:
            x0 = y0 = x1 = 0.0

        is_newline = (prev_y0 is not None) and (abs(y0 - prev_y0) > y_threshold)
        is_gap = (prev_x1 is not None) and (not is_newline) and ((x0 - prev_x1) > x_gap_threshold)

        if is_newline:
            flush()
            tokens.append(TOKEN_NL)
            token_to_char_idxs.append(None)
            pretty_parts.append("\n")
            prev_x1 = None
        elif is_gap:
            flush()
            tokens.append(TOKEN_GAP)
            token_to_char_idxs.append(None)
            pretty_parts.append(" ")

        if curr_cat is None:
            curr_cat = cat
        elif cat != curr_cat:
            flush()
            curr_cat = cat

        curr_chars.append(ch)
        curr_idxs.append(idx)
        pretty_parts.append(ch)

        prev_y0 = y0
        prev_x1 = x1

    flush()

    pretty_text = "".join(pretty_parts)

    return tokens, token_to_char_idxs, pretty_text

class ViewComparisonTextDialog(QDialog):
    """Extracted text confirmation window"""
    def __init__(self, left_text, right_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("비교 대상 텍스트 데이터 확인")
        self.resize(900, 700)
        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 10))
        
        def format_text(txt):
            if not txt: return "<i style='color:red;'>데이터가 없습니다.</i>"
            return txt.replace('\n', '<br>')

        content = f"<h3>🔍 추출 엔진 처리 데이터 (v{VERSION})</h3><hr>"
        content += "<h4>📄 [PDF 1]</h4>"
        content += f"<div style='background:#f9f9f9; padding:15px; border:1px solid #ddd; border-radius:5px;'>{format_text(left_text)}</div><hr>"
        content += "<h4>📄 [PDF 2]</h4>"
        content += f"<div style='background:#f9f9f9; padding:15px; border:1px solid #ddd; border-radius:5px;'>{format_text(right_text)}</div>"
        
        self.text_edit.setHtml(content)
        layout.addWidget(self.text_edit)
        
        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("📋 전체 복사")
        copy_btn.clicked.connect(lambda: [QApplication.clipboard().setText(self.text_edit.toPlainText()), QMessageBox.information(self, "성공", "복사되었습니다.")])
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(copy_btn); btn_layout.addStretch(); btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

class LoadingOverlay(QWidget):
    """Waiting screen for processing"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.icon_opacity = QGraphicsOpacityEffect(self)

        layout = QVBoxLayout(self)
        self.bg_frame = QFrame()
        self.bg_frame.setStyleSheet("background-color: rgba(255, 255, 255, 140); border-radius: 40px;")
        
        f_layout = QVBoxLayout(self.bg_frame)
        self.icon_label = QLabel()
        self.icon_label.setGraphicsEffect(self.icon_opacity)
        
        logo_path = get_resource_path('posid_logo.png')
        if os.path.exists(logo_path):
            self.icon_label.setPixmap(QPixmap(logo_path).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.icon_label.setText("⌛")
            self.icon_label.setStyleSheet("font-size: 50px; color: #004b93;")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.msg = QLabel("처리 중...")
        self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg.setStyleSheet("font-size: 14px; font-weight: bold; color: #444;")
        
        f_layout.addStretch(); f_layout.addWidget(self.icon_label); f_layout.addWidget(self.msg); f_layout.addStretch()
        layout.addStretch(); layout.addWidget(self.bg_frame, 0, Qt.AlignmentFlag.AlignCenter); layout.addStretch()
        self.hide()

    def start_animation(self, message="처리 중...", faded_icon=False):
        self.msg.setText(f"<b>{message}</b>")
        self.icon_opacity.setOpacity(0.15 if faded_icon else 0.6) 
        self.show(); self.setGeometry(self.parent().rect())
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(300); self.anim.setStartValue(0.0); self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic); self.anim.start()

    def stop_animation(self):
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
        if self.is_selecting:
            self.selection_end = event.pos(); self.update()
            
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
            painter = QPainter(self)
            painter.setBrush(QColor(0, 120, 255, 60))
            painter.setPen(QPen(QColor(0, 0, 255), 2, Qt.PenStyle.DashLine))
            rect = QRect(self.selection_start, self.selection_end).normalized()
            painter.drawRect(rect)
            painter.end()

    def clear_selection(self):
        self.selection_start = None; self.selection_end = None; self.update()

class PDFViewer(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.container = QWidget(); self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(0, 0, 0, 0); self.setWidget(self.container)
        self.pdf_doc = None; self.page_labels = []; self.scale = 1.5
        self.char_data = []; self.word_highlights = {}; self.last_compared_area = {}; self.pending_selection_rect = None

    def load_pdf(self, path):
        try:
            self.pdf_doc = fitz.open(path); self.reload_pages(); return True
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
        self.char_data = [] 
        self.extract_and_process_text(page_num, rect)

    def extract_and_process_text(self, page_num, rect):
        """Coordinate-based extraction (Bug Fix for KeyError)"""
        x0, y0, x1, y1 = rect.x()/self.scale, rect.y()/self.scale, (rect.x()+rect.width())/self.scale, (rect.y()+rect.height())/self.scale
        fitz_rect = fitz.Rect(x0, y0, x1, y1); page = self.pdf_doc.load_page(page_num); raw_dict = page.get_text("rawdict", clip=fitz_rect)
        all_raw_chars = []
        for block in raw_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    for char in span.get("chars", []):
                        c = char['c']
                        if '가' <= c <= '힣' or 'ㄱ' <= c <= 'ㅎ' or c.isdigit() or ('a' <= c.lower() <= 'z') or c == ' ':
                            all_raw_chars.append({
                                'char': c.lower() if 'a' <= c.lower() <= 'z' else c, 
                                'bbox': char['bbox'], 
                                'y': char['bbox'][1], 
                                'x': char['bbox'][0]
                            })
        if not all_raw_chars: return
        all_raw_chars.sort(key=lambda x: x['y'])
        grouped = []
        if all_raw_chars:
            curr = [all_raw_chars[0]]
            for i in range(1, len(all_raw_chars)):
                if all_raw_chars[i]['y'] - curr[-1]['y'] < 5.0: curr.append(all_raw_chars[i])
                else: grouped.append(curr); curr = [all_raw_chars[i]]
            grouped.append(curr)
        
        final = []
        for line in grouped:
            line.sort(key=lambda x: x['x'])
            for c in line:
                if c['char'].strip() == "": continue
                # Maintain complete dict object to avoid KeyError: 'x'
                if not final or not (c['char'] == final[-1]['char'] and abs(c['x'] - final[-1]['x']) < 2.5):
                    final.append(c)
        
        self.char_data = [{'char': item['char'], 'bbox': item['bbox'], 'page': page_num} for item in final]

    def zoom_in(self): self.scale *= 1.2; self.reload_pages()
    def zoom_out(self): self.scale /= 1.2; self.reload_pages()
    def clear_all_data(self):
        self.word_highlights.clear(); self.last_compared_area.clear(); self.char_data.clear(); self.pending_selection_rect = None
        for lbl in self.page_labels: lbl.clear_selection()
        self.reload_pages()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PDF 텍스트 비교 v{VERSION}")
        self.setGeometry(100, 100, 1600, 950)
        
        # Load Window Icon correctly for EXE build
        ico_path = get_resource_path('posid_logo.ico')
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))
        
        main_widget = QWidget(); self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget); layout.setSpacing(5)
        
        # --- Toolbar ---
        top_bar = QHBoxLayout()
        self.btn_load1 = QPushButton("📄 PDF 1 열기"); self.btn_load2 = QPushButton("📄 PDF 2 열기")
        btn_style = f"background:{COLOR_MAIN_BLUE}; color:white; font-weight:bold; height:36px; padding:0 15px; border-radius:4px;"
        self.btn_load1.setStyleSheet(btn_style); self.btn_load2.setStyleSheet(btn_style)
        top_bar.addWidget(self.btn_load1); top_bar.addWidget(self.btn_load2); top_bar.addStretch()
        
        self.btn_compare = QPushButton("🔍 비교 실행")
        self.btn_compare.setStyleSheet(f"background-color:{COLOR_COMPARE_BTN}; color:white; font-weight:bold; font-size:15px; height:42px; width:350px; border-radius:6px;")
        top_bar.addWidget(self.btn_compare); top_bar.addStretch()
        
        self.btn_view_text = QPushButton("📝 추출 데이터 확인"); self.btn_reset = QPushButton("비교결과초기화"); self.btn_info = QPushButton("i")
        self.btn_view_text.setStyleSheet(btn_style); self.btn_reset.setStyleSheet(btn_style)
        self.btn_info.setFixedSize(30, 36)
        self.btn_info.setStyleSheet(f"background:{COLOR_INFO_BTN}; border:1px solid #FBC02D; font-weight:bold; color:#5D4037; font-family:'Georgia'; font-size:18px; border-radius:4px;")
        top_bar.addWidget(self.btn_view_text); top_bar.addWidget(self.btn_reset); top_bar.addWidget(self.btn_info)
        layout.addLayout(top_bar)
        
        # --- PDF Viewers ---
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

        # --- Guide Panel (1:3 Split) ---
        guide_frame = QFrame(); guide_frame.setStyleSheet("background:#f9f9f9; border:1px solid #ddd; border-radius:6px;")
        g_layout = QHBoxLayout(guide_frame); g_layout.setContentsMargins(15, 10, 15, 10)
        
        legend_html = (
            f"<b>🎨 하이라이트 범례</b><br>"
            f"<span style='color:{COLOR_P1.name()}; background:{COLOR_P1.name()};'>■</span> PDF1 삭제/변경 (원본에서 사라진 문구)<br>"
            f"<span style='color:{COLOR_P2.name()}; background:{COLOR_P2.name()};'>■</span> PDF2 추가/변경 (새로 들어온 문구)<br>"
            f"<span style='color:rgba(0,120,255,0.6);'>■</span> 최근 비교가 진행된 영역"
        )
        leg_label = QLabel(legend_html); leg_label.setStyleSheet("font-size:11px; line-height:1.6;"); g_layout.addWidget(leg_label, 1)
        
        caution_widget = QWidget(); caution_layout = QHBoxLayout(caution_widget); caution_layout.setContentsMargins(0,0,0,0)
        col1 = QLabel(
            "<b>⚠️ 주의</b><br>"
            "1. 본 프로그램은 <b style='color:red;'>한글, 영문, 숫자</b>만을 정규화 대조합니다.<br>"
            "2. 모든 공백을 제거하고 분석하므로 <b style='color:red;'>띄어쓰기 오류는 검증되지 않습니다.</b>"
        )
        col2 = QLabel(
            "<br>" 
            "3. 표(Table) 추출 시 셀 내용이 섞일 수 있으므로 반드시 <b style='color:red;'>셀 단위 드래그</b>를 권장합니다.<br>"
            "4. 긴 복합어는 구조 차이로 <b style='color:red;'>한쪽만 하이라이트</b>될 수 있으니 대조가 필요합니다."
        )
        for c in [col1, col2]: c.setStyleSheet("font-size:11px; color:#444; line-height:1.6;"); caution_layout.addWidget(c)
        g_layout.addWidget(caution_widget, 3); layout.addWidget(guide_frame)

        self.loading = LoadingOverlay(self); self.last_s1 = ""; self.last_s2 = ""
        self.btn_load1.clicked.connect(self.load_p1); self.btn_load2.clicked.connect(self.load_p2)
        self.btn_compare.clicked.connect(lambda: [self.loading.start_animation("비교 분석 중..."), QTimer.singleShot(50, self.run_comparison)])
        self.btn_reset.clicked.connect(lambda: [self.loading.start_animation("비교결과 초기화 중...", faded_icon=True), QTimer.singleShot(800, self.reset_all)])
        self.btn_view_text.clicked.connect(self.show_text_dialog); self.btn_info.clicked.connect(self.show_info)
        self.btn_z1_p.clicked.connect(self.viewer1.zoom_in); self.btn_z1_m.clicked.connect(self.viewer1.zoom_out)
        self.btn_z2_p.clicked.connect(self.viewer2.zoom_in); self.btn_z2_m.clicked.connect(self.viewer2.zoom_out)

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
        try: self.viewer1.clear_all_data(); self.viewer2.clear_all_data(); self.last_s1 = ""; self.last_s2 = ""
        finally: self.loading.stop_animation()

    def run_comparison(self):
        try:
            if not self.viewer1.char_data or not self.viewer2.char_data:
                QMessageBox.warning(self, "경고", "양쪽 비교 영역을 먼저 드래그해주세요."); return

            # Remember the last compared area (for blue overlay)
            self.viewer1.last_compared_area.clear(); self.viewer2.last_compared_area.clear()
            for v in [self.viewer1, self.viewer2]:
                if v.pending_selection_rect:
                    p, r = v.pending_selection_rect
                    v.last_compared_area[p] = [r]

            # Build token streams (digit/alpha/hangul runs + structural boundaries)
            t1, map1, pretty1 = build_token_stream(self.viewer1.char_data)
            t2, map2, pretty2 = build_token_stream(self.viewer2.char_data)

            # For "추출 데이터 확인" window
            self.last_s1 = pretty1
            self.last_s2 = pretty2

            # Token-based diff: prevents partial digit matching (e.g. phone number "2"/"21" getting matched elsewhere)
            matcher = SequenceMatcher(None, t1, t2, autojunk=False)
            opcodes = matcher.get_opcodes()

            if DEBUG_DIFF:
                try:
                    debug_dir = os.path.join(os.path.abspath("."), "pdf_compare_debug")
                    os.makedirs(debug_dir, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    with open(os.path.join(debug_dir, f"opcodes_{ts}.txt"), "w", encoding="utf-8") as f:
                        for tag, i1, i2, j1, j2 in opcodes:
                            f.write(f"{tag}\tA[{i1}:{i2}]\tB[{j1}:{j2}]\t{t1[i1:i2]}\t{t2[j1:j2]}\n")
                except Exception:
                    pass

            for tag, i1, i2, j1, j2 in opcodes:
                if tag == 'equal':
                    continue

                if tag in ('delete', 'replace'):
                    for tok_i in range(i1, i2):
                        idxs = map1[tok_i]
                        if not idxs:
                            continue  # boundary token (NL/GAP)
                        for char_idx in idxs:
                            self.add_hl(self.viewer1, self.viewer1.char_data[char_idx], COLOR_P1)

                if tag in ('insert', 'replace'):
                    for tok_j in range(j1, j2):
                        idxs = map2[tok_j]
                        if not idxs:
                            continue  # boundary token (NL/GAP)
                        for char_idx in idxs:
                            self.add_hl(self.viewer2, self.viewer2.char_data[char_idx], COLOR_P2)

            for v in [self.viewer1, self.viewer2]:
                for lbl in v.page_labels:
                    lbl.clear_selection()
                v.reload_pages()
        finally:
            self.loading.stop_animation()


    def show_info(self):
        d = QDialog(self); d.setWindowTitle("정보"); d.setFixedSize(420, 320)
        l = QVBoxLayout(d); l.setContentsMargins(30, 30, 30, 30)
        img_p = get_resource_path('posid_logo.png')
        if os.path.exists(img_p):
            img = QLabel(); img.setPixmap(QPixmap(img_p).scaled(200, 80, Qt.AspectRatioMode.KeepAspectRatio)); img.setAlignment(Qt.AlignmentFlag.AlignCenter); l.addWidget(img)
        t = QLabel(f"<div style='text-align:center;'><h2 style='color:#004b93;'>PDF 텍스트 비교</h2><b>버전:</b> {VERSION}<br><b>배포일:</b> {RELEASE_DATE}<br><br><b>제작:</b> {DEVELOPER}</div>"); l.addWidget(t)
        btn = QPushButton("확인"); btn.setFixedHeight(35); btn.clicked.connect(d.accept); l.addStretch(); l.addWidget(btn); d.exec()

    def show_text_dialog(self):
        if not self.last_s1 and not self.last_s2: QMessageBox.information(self, "안내", "최근 비교 데이터가 없습니다."); return
        ViewComparisonTextDialog(self.last_s1, self.last_s2, self).exec()

    def add_hl(self, viewer, info, color):
        p = info['page']
        if p not in viewer.word_highlights: viewer.word_highlights[p] = []
        if not any(h[0] == info['bbox'] and h[1] == color for h in viewer.word_highlights[p]):
            viewer.word_highlights[p].append((info['bbox'], color))

    def resizeEvent(self, event):
        if self.loading.isVisible():
            self.loading.setGeometry(self.rect())
        super().resizeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setFont(QFont("Malgun Gothic", 9))
    win = MainWindow(); win.show(); sys.exit(app.exec())