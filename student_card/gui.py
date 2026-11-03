"""
PySide6 Graphical Interface for StudentCardStudio.
"""
import sys
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QCheckBox,
    QFileDialog, QMessageBox, QProgressBar, QGroupBox
)

from student_card.core import batch_generate_cards, batch_crop_eclass_only

TRANSLATIONS = {
    "zh": {
        "title": "學生證與相片製作系統 - StudentCardStudio",
        "lang_switch": "English",
        "tab_cards": "1. 批量製作學生證",
        "tab_crop": "2. 僅批量 eClass 裁剪",
        "lbl_excel": "學生名冊 (Excel):",
        "lbl_photos": "學生相片目錄:",
        "lbl_template_front": "正面模板 (PNG/JPG):",
        "lbl_template_back": "背面模板 (可選，供雙面 PDF):",
        "lbl_output": "輸出目錄:",
        "chk_smart_bg": "啟用綠幕智能退底（綠幕拍攝請勾選，會自動去背並補純白底）",
        "chk_smart_bg_tip": "一般白底拍攝請勿勾選，可保留最佳畫質與細節。",
        "chk_export_pdf": "同時生成 A4 雙面列印 PDF (8張/頁，自動對齊正背面)",
        "chk_export_3x4": "同時生成 3x4 排版 PDF (供快速列印檢閱, 12張/頁)",
        "btn_generate_cards": "開始製作學生證",
        "lbl_crop_src": "原始相片目錄:",
        "lbl_crop_out": "裁剪輸出目錄:",
        "btn_run_crop": "開始批量 eClass 裁剪",
        "browse": "瀏覽...",
        "ready": "準備就緒",
        "processing": "正在處理... [{current}/{total}] {desc}",
        "success_title": "完成",
        "success_cards": "批量製作完成！\n成功: {success}，失敗: {failed}\n\n已保存：\n1. 單張卡片 -> single_cards/\n2. eClass 裁剪相片 -> cropped_photos/\n3. 雙面列印 PDF -> student_cards_print_A4.pdf\n4. 3x4 檢閱 PDF -> student_cards_review_3x4.pdf",
        "success_crop": "eClass 裁剪完成！\n成功: {success}，失敗: {failed}",
        "error_title": "錯誤",
        "missing_fields": "請填寫所有必要的檔案路徑（名冊、相片、正面模板、輸出目錄）！",
    },
    "en": {
        "title": "Student Card Studio",
        "lang_switch": "繁體中文",
        "tab_cards": "1. Batch Generate Cards",
        "tab_crop": "2. eClass Crop Only",
        "lbl_excel": "Student List (Excel):",
        "lbl_photos": "Photos Directory:",
        "lbl_template_front": "Front Template (PNG/JPG):",
        "lbl_template_back": "Back Template (Optional):",
        "lbl_output": "Output Directory:",
        "chk_smart_bg": "Enable Green Screen Matting (Removes green & fills white)",
        "chk_smart_bg_tip": "Leave unchecked for standard white-background photos.",
        "chk_export_pdf": "Generate A4 Double-Sided Print PDF (8 cards/page)",
        "chk_export_3x4": "Generate 3x4 Review PDF (12 cards/page)",
        "btn_generate_cards": "Generate Cards",
        "lbl_crop_src": "Source Photos Directory:",
        "lbl_crop_out": "Crop Output Directory:",
        "btn_run_crop": "Run Batch eClass Crop",
        "browse": "Browse...",
        "ready": "Ready",
        "processing": "Processing... [{current}/{total}] {desc}",
        "success_title": "Completed",
        "success_cards": "Generation completed!\nSuccess: {success}, Failed: {failed}\n\nSaved:\n1. Single Cards -> single_cards/\n2. Cropped Photos -> cropped_photos/\n3. Double-Sided PDF -> student_cards_print_A4.pdf\n4. Review PDF -> student_cards_review_3x4.pdf",
        "success_crop": "eClass crop completed!\nSuccess: {success}, Failed: {failed}",
        "error_title": "Error",
        "missing_fields": "Please provide all required paths (Excel, Photos, Front Template, Output)!",
    }
}

class WorkerThread(QThread):
    progress_signal = Signal(int, int, str)
    finished_signal = Signal(object)

    def __init__(self, task_type, kwargs):
        super().__init__()
        self.task_type = task_type
        self.kwargs = kwargs

    def run(self):
        def progress_cb(current, total, desc):
            self.progress_signal.emit(current, total, desc)

        self.kwargs["progress_callback"] = progress_cb
        if self.task_type == "cards":
            stats = batch_generate_cards(**self.kwargs)
        else:
            stats = batch_crop_eclass_only(**self.kwargs)
        self.finished_signal.emit(stats)

class StudentCardMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.lang = "zh"
        self._init_ui()
        self.apply_language()

    def t(self, key):
        return TRANSLATIONS[self.lang].get(key, "")

    def toggle_language(self):
        self.lang = "en" if self.lang == "zh" else "zh"
        self.apply_language()

    def _init_ui(self):
        self.resize(780, 580)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 10, 15, 15)

        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.btn_lang = QPushButton()
        self.btn_lang.setFixedWidth(110)
        self.btn_lang.clicked.connect(self.toggle_language)
        top_bar.addWidget(self.btn_lang)
        main_layout.addLayout(top_bar)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.tab_cards = QWidget()
        self._setup_cards_tab()
        self.tabs.addTab(self.tab_cards, "")

        self.tab_crop = QWidget()
        self._setup_crop_tab()
        self.tabs.addTab(self.tab_crop, "")

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.lbl_status = QLabel()
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.lbl_status)

    def _setup_cards_tab(self):
        layout = QVBoxLayout(self.tab_cards)
        self.browse_buttons = []

        def make_row(lbl_attr, edit_attr, browse_cmd):
            row = QHBoxLayout()
            lbl = QLabel()
            lbl.setFixedWidth(200)
            setattr(self, lbl_attr, lbl)
            edit = QLineEdit()
            setattr(self, edit_attr, edit)
            btn = QPushButton()
            btn.clicked.connect(browse_cmd)
            self.browse_buttons.append(btn)
            row.addWidget(lbl)
            row.addWidget(edit)
            row.addWidget(btn)
            layout.addLayout(row)

        make_row("lbl_c_excel", "edit_c_excel", lambda: self._browse_file(self.edit_c_excel, "Excel (*.xlsx *.xls)"))
        make_row("lbl_c_photos", "edit_c_photos", lambda: self._browse_dir(self.edit_c_photos))
        make_row("lbl_c_front", "edit_c_front", lambda: self._browse_file(self.edit_c_front, "Images (*.png *.jpg *.jpeg)"))
        make_row("lbl_c_back", "edit_c_back", lambda: self._browse_file(self.edit_c_back, "Images (*.png *.jpg *.jpeg)"))
        make_row("lbl_c_output", "edit_c_output", lambda: self._browse_dir(self.edit_c_output))

        self.group_options = QGroupBox()
        group_layout = QVBoxLayout(self.group_options)

        self.chk_smart_bg = QCheckBox()
        self.chk_smart_bg.setChecked(False)
        self.lbl_smart_bg_tip = QLabel()
        self.lbl_smart_bg_tip.setStyleSheet("color: gray;")
        
        self.chk_export_pdf = QCheckBox()
        self.chk_export_pdf.setChecked(True)
        
        self.chk_export_3x4 = QCheckBox()
        self.chk_export_3x4.setChecked(True)

        group_layout.addWidget(self.chk_smart_bg)
        group_layout.addWidget(self.lbl_smart_bg_tip)
        group_layout.addWidget(self.chk_export_pdf)
        group_layout.addWidget(self.chk_export_3x4)
        layout.addWidget(self.group_options)

        self.btn_gen_cards = QPushButton()
        self.btn_gen_cards.setFixedHeight(42)
        self.btn_gen_cards.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.btn_gen_cards.clicked.connect(self._start_cards)
        layout.addWidget(self.btn_gen_cards)
        layout.addStretch()

    def _setup_crop_tab(self):
        layout = QVBoxLayout(self.tab_crop)
        def make_row(lbl_attr, edit_attr, browse_cmd):
            row = QHBoxLayout()
            lbl = QLabel()
            lbl.setFixedWidth(180)
            setattr(self, lbl_attr, lbl)
            edit = QLineEdit()
            setattr(self, edit_attr, edit)
            btn = QPushButton()
            btn.clicked.connect(browse_cmd)
            self.browse_buttons.append(btn)
            row.addWidget(lbl)
            row.addWidget(edit)
            row.addWidget(btn)
            layout.addLayout(row)

        make_row("lbl_cr_src", "edit_cr_src", lambda: self._browse_dir(self.edit_cr_src))
        make_row("lbl_cr_out", "edit_cr_out", lambda: self._browse_dir(self.edit_cr_out))

        self.btn_gen_crop = QPushButton()
        self.btn_gen_crop.setFixedHeight(42)
        self.btn_gen_crop.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.btn_gen_crop.clicked.connect(self._start_crop)
        layout.addWidget(self.btn_gen_crop)
        layout.addStretch()

    def apply_language(self):
        self.setWindowTitle(self.t("title"))
        self.btn_lang.setText(self.t("lang_switch"))

        self.tabs.setTabText(0, self.t("tab_cards"))
        self.tabs.setTabText(1, self.t("tab_crop"))

        self.lbl_c_excel.setText(self.t("lbl_excel"))
        self.lbl_c_photos.setText(self.t("lbl_photos"))
        self.lbl_c_front.setText(self.t("lbl_template_front"))
        self.lbl_c_back.setText(self.t("lbl_template_back"))
        self.lbl_c_output.setText(self.t("lbl_output"))

        self.chk_smart_bg.setText(self.t("chk_smart_bg"))
        self.lbl_smart_bg_tip.setText(self.t("chk_smart_bg_tip"))
        self.chk_export_pdf.setText(self.t("chk_export_pdf"))
        self.chk_export_3x4.setText(self.t("chk_export_3x4"))
        self.btn_gen_cards.setText(self.t("btn_generate_cards"))

        self.lbl_cr_src.setText(self.t("lbl_crop_src"))
        self.lbl_cr_out.setText(self.t("lbl_crop_out"))
        self.btn_gen_crop.setText(self.t("btn_run_crop"))

        for btn in self.browse_buttons:
            btn.setText(self.t("browse"))

        if not self.lbl_status.text() or self.lbl_status.text() in ["準備就緒", "Ready"]:
            self.lbl_status.setText(self.t("ready"))

    def _browse_file(self, target_edit, file_filter):
        path, _ = QFileDialog.getOpenFileName(self, self.t("browse"), "", file_filter)
        if path:
            target_edit.setText(path)

    def _browse_dir(self, target_edit):
        path = QFileDialog.getExistingDirectory(self, self.t("browse"))
        if path:
            target_edit.setText(path)

    def _on_progress(self, current, total, desc):
        pct = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(self.t("processing").format(current=current, total=total, desc=desc))

    def _start_cards(self):
        excel = self.edit_c_excel.text().strip()
        photos = self.edit_c_photos.text().strip()
        front = self.edit_c_front.text().strip()
        back = self.edit_c_back.text().strip()
        output = self.edit_c_output.text().strip()
        
        use_smart_bg = self.chk_smart_bg.isChecked()
        export_pdf = self.chk_export_pdf.isChecked()
        export_3x4_pdf = self.chk_export_3x4.isChecked()

        if not (excel and photos and front and output):
            QMessageBox.critical(self, self.t("error_title"), self.t("missing_fields"))
            return

        self.btn_gen_cards.setEnabled(False)
        self.worker = WorkerThread("cards", {
            "excel_path": excel,
            "photos_dir": photos,
            "front_template": front,
            "back_template": back if back else None,
            "output_dir": output,
            "use_smart_bg": use_smart_bg,
            "export_pdf": export_pdf,
            "export_3x4_pdf": export_3x4_pdf,
        })
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.finished_signal.connect(self._on_cards_finish)
        self.worker.start()

    def _on_cards_finish(self, stats):
        self.btn_gen_cards.setEnabled(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText(self.t("ready"))
        msg = self.t("success_cards").format(success=stats.success, failed=stats.failed)
        if stats.errors:
            msg += "\n\n錯誤詳情 (前5項):\n" + "\n".join(stats.errors[:5])
        QMessageBox.information(self, self.t("success_title"), msg)

    def _start_crop(self):
        src = self.edit_cr_src.text().strip()
        out = self.edit_cr_out.text().strip()

        if not (src and out):
            QMessageBox.critical(self, self.t("error_title"), self.t("missing_fields"))
            return

        self.btn_gen_crop.setEnabled(False)
        self.worker = WorkerThread("crop", {
            "photos_dir": src,
            "output_dir": out,
        })
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.finished_signal.connect(self._on_crop_finish)
        self.worker.start()

    def _on_crop_finish(self, stats):
        self.btn_gen_crop.setEnabled(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText(self.t("ready"))
        msg = self.t("success_crop").format(success=stats.success, failed=stats.failed)
        if stats.errors:
            msg += "\n\n錯誤詳情:\n" + "\n".join(stats.errors[:5])
        QMessageBox.information(self, self.t("success_title"), msg)

def main():
    app = QApplication(sys.argv)
    window = StudentCardMainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()