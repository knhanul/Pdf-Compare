import sys
import fitz  # PyMuPDF
import re
import traceback
import os
from datetime import datetime
from difflib import SequenceMatcher

# 버전 정보 및 배포 정보
VERSION = '1.0.8' 
RELEASE_DATE = os.environ.get('PDF_COMPARE_RELEASE_DATE', '2025-12-31')
DEVELOPER = '우체국금융개발원 디지털정보전략실 시스템품질팀'

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QScrollArea, QMessageBox, QTextEdit,
    QDialog, QFrame, QGraphicsOpacityEffect
)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QIcon, QFont
from PyQt6.QtCore import Qt, QRect, QTimer, QSize, QPropertyAnimation, QEasingCurve

# 전용 색상 정의
COLOR_P1 = QColor(255, 0, 255, 70)   # 마젠타
COLOR_P2 = QColor(0, 200, 100, 70)   # 에메랄드
COLOR_AREA = QColor(0, 120, 255, 15) # 최근 비교 구역
COLOR_MAIN_BLUE = "#004b93"
COLOR_COMPARE_BTN = "#FF6D00"        # 중앙 주황색
COLOR_INFO_BTN = "#FFEB3B"           # 노란색 정보 버튼

class ViewComparisonTextDialog(QDialog):
    """추출 데이터 확인창"""
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
    """작업 대기 안내 화면"""
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
        
        if os.path.exists('posid_logo.png'):
            self.icon_label.setPixmap(QPixmap('posid_logo.png').scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
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
        self.icon_opacity.setOpacity(0.12 if faded_icon else 0.5) 
        self.show(); self.setGeometry(self.parent().rect())
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(250); self.anim.setStartValue(0.0); self.anim.setEndValue(1.0)
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
        """좌표 기반 정밀 추출 (KeyError 방지 및 로직 개선)"""
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
                # 좌표 비교 시 'x' 키가 존재하는지 확실히 보장
                if not final or not (c['char'] == final[-1]['char'] and abs(c['x'] - final[-1]['x']) < 2.5):
                    final.append(c)
        
        # 최종 데이터에 page 정보 주입
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
        if os.path.exists('posid_logo.ico'): self.setWindowIcon(QIcon('posid_logo.ico'))
        
        main_widget = QWidget(); self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget); layout.setSpacing(5)
        
        # --- 상단 툴바 ---
        top_bar = QHBoxLayout()
        # [왼쪽] PDF 열기
        self.btn_load1 = QPushButton("📄 PDF 1 열기"); self.btn_load2 = QPushButton("📄 PDF 2 열기")
        btn_l_style = f"background:{COLOR_MAIN_BLUE}; color:white; font-weight:bold; height:36px; padding:0 15px; border-radius:4px;"
        self.btn_load1.setStyleSheet(btn_l_style); self.btn_load2.setStyleSheet(btn_l_style)
        top_bar.addWidget(self.btn_load1); top_bar.addWidget(self.btn_load2); top_bar.addStretch()
        
        # [중앙] 비교 실행 (강조)
        self.btn_compare = QPushButton("🔍 비교 실행")
        self.btn_compare.setStyleSheet(f"background-color:{COLOR_COMPARE_BTN}; color:white; font-weight:bold; font-size:15px; height:42px; width:350px; border-radius:6px;")
        top_bar.addWidget(self.btn_compare); top_bar.addStretch()
        
        # [오른쪽] 데이터 확인, 초기화, 정보
        self.btn_view_text = QPushButton("📝 추출 데이터 확인"); self.btn_reset = QPushButton("비교결과초기화"); self.btn_info = QPushButton("i")
        self.btn_view_text.setStyleSheet(btn_l_style); self.btn_reset.setStyleSheet(btn_l_style)
        self.btn_info.setFixedSize(30, 36)
        self.btn_info.setStyleSheet(f"background:{COLOR_INFO_BTN}; border:1px solid #FBC02D; font-weight:bold; color:#5D4037; font-family:'Georgia'; font-size:18px; border-radius:4px;")
        top_bar.addWidget(self.btn_view_text); top_bar.addWidget(self.btn_reset); top_bar.addWidget(self.btn_info)
        layout.addLayout(top_bar)
        
        # --- 뷰어 영역 ---
        view_area = QHBoxLayout()
        # PDF 1
        v1_box = QVBoxLayout(); v1_head = QHBoxLayout()
        self.btn_z1_p = QPushButton("확대 🔍+"); self.btn_z1_m = QPushButton("축소 🔍-")
        for b in [self.btn_z1_p, self.btn_z1_m]: b.setFixedSize(70, 24); b.setStyleSheet("font-size:11px; background:#f8f9fa; border:1px solid #ccc; border-radius:3px;")
        self.lbl_name1 = QLabel("<b>[PDF 1]</b>")
        v1_head.addWidget(self.btn_z1_p); v1_head.addWidget(self.btn_z1_m); v1_head.addWidget(self.lbl_name1); v1_head.addStretch()
        v1_box.addLayout(v1_head); self.viewer1 = PDFViewer(); v1_box.addWidget(self.viewer1); view_area.addLayout(v1_box)
        # PDF 2
        v2_box = QVBoxLayout(); v2_head = QHBoxLayout()
        self.btn_z2_p = QPushButton("확대 🔍+"); self.btn_z2_m = QPushButton("축소 🔍-")
        for b in [self.btn_z2_p, self.btn_z2_m]: b.setFixedSize(70, 24); b.setStyleSheet("font-size:11px; background:#f8f9fa; border:1px solid #ccc; border-radius:3px;")
        self.lbl_name2 = QLabel("<b>[PDF 2]</b>")
        v2_head.addWidget(self.btn_z2_p); v2_head.addWidget(self.btn_z2_m); v2_head.addWidget(self.lbl_name2); v2_head.addStretch()
        v2_box.addLayout(v2_head); self.viewer2 = PDFViewer(); v2_box.addWidget(self.viewer2); view_area.addLayout(v2_box)
        layout.addLayout(view_area)

        # --- 하단 통합 안내 패널 (1:3 비율 2단 레이아웃) ---
        guide_frame = QFrame(); guide_frame.setStyleSheet("background:#f9f9f9; border:1px solid #ddd; border-radius:6px;")
        g_layout = QHBoxLayout(guide_frame); g_layout.setContentsMargins(15, 10, 15, 10)
        
        # 왼쪽 범례 (1/4)
        leg_label = QLabel(f"<b>🎨 하이라이트 범례</b><br><span style='color:{COLOR_P1.name()};'>■</span> P1 삭제/변경(어긋남)<br><span style='color:{COLOR_P2.name()};'>■</span> P2 추가/변경(새 내용)<br><span style='color:rgba(0,120,255,0.6);'>■</span> 최근 비교 구역")
        leg_label.setStyleSheet("font-size:11px; line-height:1.5;"); g_layout.addWidget(leg_label, 1)
        
        # 오른쪽 주의 (3/4) - 2열 단나누기 효과
        caution_widget = QWidget()
        caution_layout = QHBoxLayout(caution_widget); caution_layout.setContentsMargins(0,0,0,0)
        
        col1 = QLabel(
            "<b>⚠️ 주의사항 (1/2)</b><br>"
            "1. 표(Table) 추출 시 셀 내용이 섞일 수 있으므로 반드시 <b style='color:red; font-family:Malgun Gothic;'>셀 단위 드래그</b>를 권장합니다.<br>"
            "2. 본 프로그램은 <b style='color:red; font-family:Malgun Gothic;'>한글, 영문, 숫자</b>만을 정규화 대조합니다."
        )
        col2 = QLabel(
            "<b>⚠️ 주의사항 (2/2)</b><br>"
            "3. 공백 제거 후 비교하므로 <b style='color:red; font-family:Malgun Gothic;'>띄어쓰기 오류는 검증되지 않습니다.</b><br>"
            "4. 긴 복합어(특약명 등)는 PDF 구조에 따라 <b style='color:red; font-family:Malgun Gothic;'>한쪽만 하이라이트</b>될 수 있습니다."
        )
        for c in [col1, col2]: c.setStyleSheet("font-size:11px; color:#444; line-height:1.5;"); caution_layout.addWidget(c)
        
        g_layout.addWidget(caution_widget, 3)
        layout.addWidget(guide_frame)

        self.loading = LoadingOverlay(self); self.last_s1 = ""; self.last_s2 = ""
        self.btn_load1.clicked.connect(self.load_p1); self.btn_load2.clicked.connect(self.load_p2)
        self.btn_compare.clicked.connect(lambda: [self.loading.start_animation("비교 분석 중..."), QTimer.singleShot(50, self.run_comparison)])
        # 초기화 시 아이콘 유지 시간을 위해 타이머 600ms로 연장
        self.btn_reset.clicked.connect(lambda: [self.loading.start_animation("비교결과 초기화 중...", faded_icon=True), QTimer.singleShot(600, self.reset_all)])
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
            self.viewer1.last_compared_area.clear(); self.viewer2.last_compared_area.clear()
            for v in [self.viewer1, self.viewer2]:
                if v.pending_selection_rect: p, r = v.pending_selection_rect; v.last_compared_area[p] = [r]
            self.last_s1 = "".join([d['char'] for d in self.viewer1.char_data]); self.last_s2 = "".join([d['char'] for d in self.viewer2.char_data])
            matcher = SequenceMatcher(None, self.last_s1, self.last_s2)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == 'equal': continue
                if tag in ('delete', 'replace'):
                    for idx in range(i1, i2): self.add_hl(self.viewer1, self.viewer1.char_data[idx], COLOR_P1)
                if tag in ('insert', 'replace'):
                    for idx in range(j1, j2): self.add_hl(self.viewer2, self.viewer2.char_data[idx], COLOR_P2)
            for v in [self.viewer1, self.viewer2]:
                for lbl in v.page_labels: lbl.clear_selection()
                v.reload_pages()
        finally: self.loading.stop_animation()

    def show_info(self):
        d = QDialog(self); d.setWindowTitle("정보"); d.setFixedSize(420, 320)
        l = QVBoxLayout(d); l.setContentsMargins(30, 30, 30, 30)
        if os.path.exists('posid_logo.png'):
            img = QLabel(); img.setPixmap(QPixmap('posid_logo.png').scaled(200, 80, Qt.AspectRatioMode.KeepAspectRatio)); img.setAlignment(Qt.AlignmentFlag.AlignCenter); l.addWidget(img)
        t = QLabel(f"<div style='text-align:center;'><h2 style='color:#004b93;'>PDF텍스트비교</h2><b>버전:</b> {VERSION}<br><b>배포일:</b> {RELEASE_DATE}<br><br><b>제작:</b> {DEVELOPER}</div>"); l.addWidget(t)
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
        if self.loading.isVisible(): self.loading.setGeometry(self.rect())
        super().resizeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setFont(QFont("Malgun Gothic", 9))
    win = MainWindow(); win.show(); sys.exit(app.exec())