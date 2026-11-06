"""
PySide6 Graphical Interface for StudentCardStudio.
"""
import sys
from pathlib import Path
from PySide6.QtCore import QSettings, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QCheckBox,
    QFileDialog, QMessageBox, QProgressBar, QGroupBox, QDoubleSpinBox, QScrollArea
)

from student_card.core import batch_generate_cards, batch_crop_eclass_only, batch_generate_pdfs

TRANSLATIONS = {
    "zh": {
        "title": "學生證與相片製作系統 - StudentCardStudio",
        "lang_switch": "English",
        "tab_cards": "1. 批量製作學生證",
        "tab_crop": "2. 僅批量 eClass 裁剪",
        "tab_pdf": "3. 僅生成正背面 PDF",
        "lbl_back": "統一背面圖片 (PNG/JPG):",
        "chk_student_pdfs": "同時生成每人正背面 PDF（2頁）及全班總 PDF",
        "pdf_size": "每面 PDF 尺寸（寬 × 高，mm）：",
        "pdf_fronts": "已完成的正面圖片目錄:",
        "pdf_tip": "每人 PDF 先正面後背面；總檔依檔名排序。每頁一面，非 A4 多張雙面排版。",
        "btn_pdf": "生成個別 PDF 及合併總 PDF",
        "success_pdf": "PDF 生成完成！\n成功: {success}，失敗: {failed}",
        "pdf_counts": "個別 PDF：成功 {success}、失敗 {failed}",
        "missing_pdf": "請指定正面圖片目錄、背面圖片及輸出目錄。",
        "settings_error": "無法保存設定，請檢查設定目錄權限。",
        "lbl_excel": "學生名冊 (Excel):",
        "lbl_photos": "學生相片目錄:",
        "lbl_template_front": "正面模板 (PNG/JPG):",
        "lbl_mask": "照片遮罩 (psd_mask.png):",
        "lbl_font_eng": "英文字體 (ARLRDBD.TTF):",
        "lbl_font_chi": "中文字體 (BiauKai.ttf):",
        "lbl_font_id": "學號字體 (Arial.ttf):",
        "brightness": "相片亮度（原 Colab：1.2）：",
        "resource_tip": "原版 649×1033 排版；資源留空時從模板同目錄尋找，字體未找到則用系統字體。",
        "lbl_output": "輸出目錄:",
        "chk_smart_bg": "啟用綠幕智能退底（綠幕拍攝請勾選，會自動去背並補純白底）",
        "chk_smart_bg_tip": "一般白底拍攝請勿勾選，可保留最佳畫質與細節。",
        "chk_export_3x4": "同時生成 3x4 排版 PDF (供快速列印檢閱, 12張/頁)",
        "btn_generate_cards": "開始製作學生證",
        "lbl_crop_src": "原始相片目錄:",
        "lbl_crop_out": "裁剪輸出目錄:",
        "btn_run_crop": "開始批量 eClass 裁剪",
        "browse": "瀏覽...",
        "ready": "準備就緒",
        "processing": "正在處理... [{current}/{total}] {desc}",
        "success_title": "完成",
        "success_cards": "批量製作完成！\n成功: {success}，失敗: {failed}",
        "success_crop": "eClass 裁剪完成！\n成功: {success}，失敗: {failed}",
        "error_title": "錯誤",
        "missing_fields": "請填寫所有必要的檔案路徑（名冊、相片、正面模板、輸出目錄）！",
        "missing_crop": "請指定原始相片及輸出目錄。",
        "output": "本次輸出：{path}",
        "errors": "錯誤詳情（前 5 項）：",
        "job_failed": "任務失敗，請檢查輸入後重試。",
        "busy": "任務執行中，請等待完成後再關閉視窗。",
        "options": "輸出選項",
    },
    "en": {
        "title": "Student Card Studio",
        "lang_switch": "繁體中文",
        "tab_cards": "1. Batch Generate Cards",
        "tab_crop": "2. eClass Crop Only",
        "tab_pdf": "3. Front/Back PDF Only",
        "lbl_back": "Common Back Image (PNG/JPG):",
        "chk_student_pdfs": "Create individual front/back PDFs (2 pages) and combined class PDF",
        "pdf_size": "PDF page size (width × height, mm):",
        "pdf_fronts": "Finished Front Images Directory:",
        "pdf_tip": "Each student: front then back. Combined file: filename order. One side per page, not A4 imposition.",
        "btn_pdf": "Generate Individual and Combined PDFs",
        "success_pdf": "PDF generation completed!\nSuccess: {success}, Failed: {failed}",
        "pdf_counts": "Individual PDFs: {success} succeeded, {failed} failed",
        "missing_pdf": "Please specify front images, back image, and output directory.",
        "settings_error": "Unable to save settings. Check the settings directory permissions.",
        "lbl_excel": "Student List (Excel):",
        "lbl_photos": "Photos Directory:",
        "lbl_template_front": "Front Template (PNG/JPG):",
        "lbl_mask": "Portrait Mask (psd_mask.png):",
        "lbl_font_eng": "English Font (ARLRDBD.TTF):",
        "lbl_font_chi": "Chinese Font (BiauKai.ttf):",
        "lbl_font_id": "ID Font (Arial.ttf):",
        "brightness": "Photo brightness (Colab: 1.2):",
        "resource_tip": "Original 649×1033 layout. Blank resources are found beside the template; missing fonts use system fonts.",
        "lbl_output": "Output Directory:",
        "chk_smart_bg": "Enable Green Screen Matting (Removes green & fills white)",
        "chk_smart_bg_tip": "Leave unchecked for standard white-background photos.",
        "chk_export_3x4": "Generate 3x4 Review PDF (12 cards/page)",
        "btn_generate_cards": "Generate Cards",
        "lbl_crop_src": "Source Photos Directory:",
        "lbl_crop_out": "Crop Output Directory:",
        "btn_run_crop": "Run Batch eClass Crop",
        "browse": "Browse...",
        "ready": "Ready",
        "processing": "Processing... [{current}/{total}] {desc}",
        "success_title": "Completed",
        "success_cards": "Generation completed!\nSuccess: {success}, Failed: {failed}",
        "success_crop": "eClass crop completed!\nSuccess: {success}, Failed: {failed}",
        "error_title": "Error",
        "missing_fields": "Please provide all required paths (Excel, Photos, Front Template, Output)!",
        "missing_crop": "Please specify source photos and output directories.",
        "output": "Job output: {path}",
        "errors": "Error details (first 5):",
        "job_failed": "Task failed. Check the inputs and try again.",
        "busy": "A task is running. Please wait before closing the window.",
        "options": "Output options",
    }
}

class WorkerThread(QThread):
    progress_signal = Signal(int, int, str)
    finished_signal = Signal(object)
    error_signal = Signal(str)

    def __init__(self, task_type, kwargs):
        super().__init__()
        self.task_type = task_type
        self.kwargs = dict(kwargs)
        self.result = None
        self.error = ""

    def run(self):
        def progress_cb(current, total, desc):
            self.progress_signal.emit(current, total, desc)

        try:
            tasks = {"cards": batch_generate_cards, "crop": batch_crop_eclass_only, "pdf": batch_generate_pdfs}
            if self.task_type not in tasks:
                raise ValueError(f"Unknown task: {self.task_type}")
            self.result = tasks[self.task_type](**self.kwargs, progress_callback=progress_cb)
            self.finished_signal.emit(self.result)
        except Exception as exc:
            self.error = str(exc) or type(exc).__name__
            self.error_signal.emit(self.error)

class StudentCardMainWindow(QMainWindow):
    PATH_FIELDS = (
        "edit_c_excel", "edit_c_photos", "edit_c_front", "edit_c_mask", "edit_c_font_eng",
        "edit_c_font_chi", "edit_c_font_id", "edit_c_back", "edit_c_output",
        "edit_cr_src", "edit_cr_out", "edit_p_fronts", "edit_p_back", "edit_p_output",
    )
    CHECK_FIELDS = ("chk_smart_bg", "chk_export_3x4", "chk_student_pdfs")
    NUMBER_FIELDS = ("spin_brightness", "spin_c_pdf_width", "spin_c_pdf_height",
                     "spin_p_pdf_width", "spin_p_pdf_height")

    def __init__(self, *, persist=True, settings=None):
        super().__init__()
        self.settings = (settings if settings is not None else QSettings(
            QSettings.IniFormat, QSettings.UserScope, "StudentCardStudio", "StudentCardStudio")) if persist else None
        self.lang = "zh"
        self.worker = None
        self.last_output = ""
        self.last_stats = None
        self._init_ui()
        self._restore_settings()
        self.apply_language()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(350)
        self._save_timer.timeout.connect(self.save_settings)
        for name in self.PATH_FIELDS:
            getattr(self, name).textChanged.connect(self._schedule_save)
        for name in self.CHECK_FIELDS:
            getattr(self, name).toggled.connect(self._schedule_save)
        for name in self.NUMBER_FIELDS:
            getattr(self, name).valueChanged.connect(self._schedule_save)
        self.tabs.currentChanged.connect(self._schedule_save)

    def t(self, key):
        return TRANSLATIONS[self.lang].get(key, "")

    def toggle_language(self):
        self.lang = "en" if self.lang == "zh" else "zh"
        self.apply_language()
        self._schedule_save()

    def _schedule_save(self, *_):
        if self.settings is not None:
            self._save_timer.start()

    def _restore_settings(self):
        if self.settings is None:
            return
        for name in self.PATH_FIELDS:
            value = self.settings.value(f"paths/{name}", "")
            if isinstance(value, str):
                getattr(self, name).setText(value)
        for name in self.CHECK_FIELDS:
            value = self.settings.value(f"options/{name}")
            if value is not None:
                getattr(self, name).setChecked(str(value).lower() in {"true", "1"})
        for name in self.NUMBER_FIELDS:
            try:
                value = float(self.settings.value(f"options/{name}", getattr(self, name).value()))
                # QDoubleSpinBox bounds also protect corrupt/outdated config values.
                if value == value and abs(value) != float("inf"):
                    getattr(self, name).setValue(value)
            except (TypeError, ValueError):
                pass
        language = self.settings.value("ui/language", "zh")
        self.lang = language if language in TRANSLATIONS else "zh"
        try:
            index = int(self.settings.value("ui/tab", 0))
            if 0 <= index < self.tabs.count():
                self.tabs.setCurrentIndex(index)
        except (TypeError, ValueError):
            pass

    @Slot()
    def save_settings(self):
        if self.settings is None:
            return
        for name in self.PATH_FIELDS:
            self.settings.setValue(f"paths/{name}", getattr(self, name).text())
        for name in self.CHECK_FIELDS + self.NUMBER_FIELDS:
            widget = getattr(self, name)
            value = widget.isChecked() if isinstance(widget, QCheckBox) else widget.value()
            self.settings.setValue(f"options/{name}", value)
        self.settings.setValue("ui/language", self.lang)
        self.settings.setValue("ui/tab", self.tabs.currentIndex())
        self.settings.sync()
        if self.settings.status() != QSettings.NoError:
            self.lbl_status.setText(self.t("settings_error"))

    def _init_ui(self):
        self.resize(960, 780)
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
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.tab_cards)
        self.tabs.addTab(scroll, "")

        self.tab_crop = QWidget()
        self._setup_crop_tab()
        self.tabs.addTab(self.tab_crop, "")
        self.tab_pdf = QWidget()
        self._setup_pdf_tab()
        self.tabs.addTab(self.tab_pdf, "")

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
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

        make_row("lbl_c_excel", "edit_c_excel", lambda: self._browse_file(self.edit_c_excel, "Excel (*.xlsx)"))
        make_row("lbl_c_photos", "edit_c_photos", lambda: self._browse_dir(self.edit_c_photos))
        make_row("lbl_c_front", "edit_c_front", lambda: self._browse_file(self.edit_c_front, "Images (*.png *.jpg *.jpeg)"))
        make_row("lbl_c_mask", "edit_c_mask", lambda: self._browse_file(self.edit_c_mask, "Images (*.png)"))
        make_row("lbl_c_font_eng", "edit_c_font_eng", lambda: self._browse_file(self.edit_c_font_eng, "Fonts (*.ttf *.TTF *.ttc *.otf)"))
        make_row("lbl_c_font_chi", "edit_c_font_chi", lambda: self._browse_file(self.edit_c_font_chi, "Fonts (*.ttf *.TTF *.ttc *.otf)"))
        make_row("lbl_c_font_id", "edit_c_font_id", lambda: self._browse_file(self.edit_c_font_id, "Fonts (*.ttf *.TTF *.ttc *.otf)"))
        make_row("lbl_c_back", "edit_c_back", lambda: self._browse_file(self.edit_c_back, "Images (*.png *.jpg *.jpeg)"))
        make_row("lbl_c_output", "edit_c_output", lambda: self._browse_dir(self.edit_c_output))
        self.lbl_resources = QLabel()
        self.lbl_resources.setWordWrap(True)
        layout.addWidget(self.lbl_resources)

        self.group_options = QGroupBox()
        group_layout = QVBoxLayout(self.group_options)

        self.chk_smart_bg = QCheckBox()
        self.chk_smart_bg.setChecked(False)
        self.lbl_smart_bg_tip = QLabel()
        self.lbl_smart_bg_tip.setStyleSheet("color: gray;")
        
        self.chk_export_3x4 = QCheckBox()
        self.chk_export_3x4.setChecked(True)
        self.chk_student_pdfs = QCheckBox()
        self.chk_student_pdfs.setChecked(False)
        brightness_row = QHBoxLayout()
        self.lbl_brightness = QLabel()
        self.spin_brightness = QDoubleSpinBox()
        self.spin_brightness.setRange(0.1, 3.0)
        self.spin_brightness.setSingleStep(0.05)
        self.spin_brightness.setValue(1.2)
        brightness_row.addWidget(self.lbl_brightness)
        brightness_row.addWidget(self.spin_brightness)
        brightness_row.addStretch()
        group_layout.addLayout(brightness_row)

        group_layout.addWidget(self.chk_smart_bg)
        group_layout.addWidget(self.lbl_smart_bg_tip)
        group_layout.addWidget(self.chk_export_3x4)
        group_layout.addWidget(self.chk_student_pdfs)
        self.lbl_c_pdf_size, self.spin_c_pdf_width, self.spin_c_pdf_height = self._pdf_size_row(group_layout)
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

    def _pdf_size_row(self, layout):
        row = QHBoxLayout()
        label = QLabel()
        row.addWidget(label)
        spins = []
        for index, default in enumerate((54.0, 85.6)):
            if index:
                row.addWidget(QLabel("×"))
            spin = QDoubleSpinBox()
            spin.setRange(10, 500)
            spin.setDecimals(2)
            spin.setValue(default)
            row.addWidget(spin)
            spins.append(spin)
        row.addStretch()
        layout.addLayout(row)
        return label, *spins

    def _setup_pdf_tab(self):
        layout = QVBoxLayout(self.tab_pdf)
        for label_name, edit_name, is_file in (
            ("lbl_p_fronts", "edit_p_fronts", False),
            ("lbl_p_back", "edit_p_back", True),
            ("lbl_p_output", "edit_p_output", False),
        ):
            row = QHBoxLayout()
            label, edit, button = QLabel(), QLineEdit(), QPushButton()
            label.setFixedWidth(230)
            setattr(self, label_name, label)
            setattr(self, edit_name, edit)
            if is_file:
                button.clicked.connect(lambda checked=False, edit=edit: self._browse_file(edit, "Images (*.png *.jpg *.jpeg)"))
            else:
                button.clicked.connect(lambda checked=False, edit=edit: self._browse_dir(edit))
            self.browse_buttons.append(button)
            for widget in (label, edit, button):
                row.addWidget(widget)
            layout.addLayout(row)
        self.lbl_p_pdf_size, self.spin_p_pdf_width, self.spin_p_pdf_height = self._pdf_size_row(layout)
        self.lbl_pdf_tip = QLabel()
        self.lbl_pdf_tip.setWordWrap(True)
        layout.addWidget(self.lbl_pdf_tip)
        self.btn_gen_pdf = QPushButton()
        self.btn_gen_pdf.setFixedHeight(42)
        self.btn_gen_pdf.clicked.connect(self._start_pdf)
        layout.addWidget(self.btn_gen_pdf)
        layout.addStretch()

    def apply_language(self):
        self.setWindowTitle(self.t("title"))
        self.btn_lang.setText(self.t("lang_switch"))

        self.tabs.setTabText(0, self.t("tab_cards"))
        self.tabs.setTabText(1, self.t("tab_crop"))
        self.tabs.setTabText(2, self.t("tab_pdf"))

        self.lbl_c_excel.setText(self.t("lbl_excel"))
        self.lbl_c_photos.setText(self.t("lbl_photos"))
        self.lbl_c_front.setText(self.t("lbl_template_front"))
        for label, key in ((self.lbl_c_mask, "lbl_mask"), (self.lbl_c_font_eng, "lbl_font_eng"),
                           (self.lbl_c_font_chi, "lbl_font_chi"), (self.lbl_c_font_id, "lbl_font_id"),
                           (self.lbl_brightness, "brightness"), (self.lbl_resources, "resource_tip")):
            label.setText(self.t(key))
        self.lbl_c_output.setText(self.t("lbl_output"))
        self.lbl_c_back.setText(self.t("lbl_back"))
        self.chk_student_pdfs.setText(self.t("chk_student_pdfs"))
        for label in (self.lbl_c_pdf_size, self.lbl_p_pdf_size):
            label.setText(self.t("pdf_size"))
        self.lbl_p_fronts.setText(self.t("pdf_fronts"))
        self.lbl_p_back.setText(self.t("lbl_back"))
        self.lbl_p_output.setText(self.t("lbl_output"))
        self.lbl_pdf_tip.setText(self.t("pdf_tip"))
        self.btn_gen_pdf.setText(self.t("btn_pdf"))

        self.chk_smart_bg.setText(self.t("chk_smart_bg"))
        self.lbl_smart_bg_tip.setText(self.t("chk_smart_bg_tip"))
        self.group_options.setTitle(self.t("options"))
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
        initial = target_edit.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, self.t("browse"), initial, file_filter)
        if path:
            target_edit.setText(path)

    def _browse_dir(self, target_edit):
        path = QFileDialog.getExistingDirectory(self, self.t("browse"), target_edit.text().strip() or str(Path.home()))
        if path:
            target_edit.setText(path)

    def _on_progress(self, current, total, desc):
        pct = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(self.t("processing").format(current=current, total=total, desc=desc))

    def _start_cards(self):
        if self.worker is not None:
            return
        excel = self.edit_c_excel.text().strip()
        photos = self.edit_c_photos.text().strip()
        front = self.edit_c_front.text().strip()
        output = self.edit_c_output.text().strip()
        
        use_smart_bg = self.chk_smart_bg.isChecked()
        export_3x4_pdf = self.chk_export_3x4.isChecked()

        if not (excel and photos and front and output):
            QMessageBox.critical(self, self.t("error_title"), self.t("missing_fields"))
            return

        self._start_worker("cards", {
            "excel_path": excel,
            "photos_dir": photos,
            "front_template": front,
            "output_dir": output,
            "use_smart_bg": use_smart_bg,
            "export_3x4_pdf": export_3x4_pdf,
            "mask_path": self.edit_c_mask.text().strip(),
            "font_eng_path": self.edit_c_font_eng.text().strip(),
            "font_chi_path": self.edit_c_font_chi.text().strip(),
            "font_id_path": self.edit_c_font_id.text().strip(),
            "brightness": self.spin_brightness.value(),
            "back_path": self.edit_c_back.text().strip(),
            "export_student_pdfs": self.chk_student_pdfs.isChecked(),
            "pdf_width_mm": self.spin_c_pdf_width.value(),
            "pdf_height_mm": self.spin_c_pdf_height.value(),
        })

    def _start_crop(self):
        if self.worker is not None:
            return
        src = self.edit_cr_src.text().strip()
        out = self.edit_cr_out.text().strip()

        if not (src and out):
            QMessageBox.critical(self, self.t("error_title"), self.t("missing_crop"))
            return

        self._start_worker("crop", {
            "photos_dir": src,
            "output_dir": out,
        })

    def _start_worker(self, task_type, kwargs):
        if self.worker is not None:
            return
        self.save_settings()
        self.last_stats = None
        self.tabs.setEnabled(False)
        self.btn_gen_cards.setEnabled(False)
        self.btn_gen_crop.setEnabled(False)
        self.btn_gen_pdf.setEnabled(False)
        self.progress_bar.setValue(0)
        self.lbl_status.setText(self.t("processing").format(current=0, total=0, desc=""))
        self.worker = WorkerThread(task_type, kwargs)
        self.worker.progress_signal.connect(self._on_progress)
        # Consume results only after QThread.finished, not before run() returns.
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _start_pdf(self):
        if self.worker is not None:
            return
        fronts, back, output = (edit.text().strip() for edit in (
            self.edit_p_fronts, self.edit_p_back, self.edit_p_output))
        if not (fronts and back and output):
            QMessageBox.critical(self, self.t("error_title"), self.t("missing_pdf"))
            return
        self._start_worker("pdf", {
            "fronts_dir": fronts, "back_path": back, "output_dir": output,
            "pdf_width_mm": self.spin_p_pdf_width.value(), "pdf_height_mm": self.spin_p_pdf_height.value(),
        })

    @Slot()
    def _worker_finished(self):
        worker = self.worker
        if worker is None:
            return
        worker.wait()
        self.worker = None
        self.tabs.setEnabled(True)
        self.btn_gen_cards.setEnabled(True)
        self.btn_gen_crop.setEnabled(True)
        self.btn_gen_pdf.setEnabled(True)
        worker.deleteLater()
        if worker.error:
            self.progress_bar.setValue(0)
            self.lbl_status.setText(self.t("job_failed"))
            QMessageBox.critical(self, self.t("error_title"), worker.error)
            return
        stats = worker.result
        self.last_stats = stats
        self.last_output = stats.output_dir
        self.progress_bar.setValue(100)
        self.lbl_status.setText(self.t("output").format(path=stats.output_dir))
        key = {"cards": "success_cards", "crop": "success_crop", "pdf": "success_pdf"}[worker.task_type]
        msg = self.t(key).format(success=stats.success, failed=stats.failed)
        msg += "\n\n" + self.t("output").format(path=stats.output_dir)
        if worker.task_type == "cards" and stats.success:
            msg += "\nsingle_cards/\ncropped_photos/"
        if stats.review_pdf:
            msg += "\n" + Path(stats.review_pdf).name
        if stats.pdf_success or stats.pdf_failed:
            msg += "\n" + self.t("pdf_counts").format(success=stats.pdf_success, failed=stats.pdf_failed)
        if stats.individual_pdf_dir:
            msg += "\n" + str(Path(stats.individual_pdf_dir).name) + "/"
        if stats.combined_pdf:
            msg += "\n" + Path(stats.combined_pdf).name
        if worker.task_type == "cards" and stats.success:
            self.edit_p_fronts.setText(str(Path(stats.output_dir) / "single_cards"))
            if not self.edit_p_back.text():
                self.edit_p_back.setText(self.edit_c_back.text() or str(Path(self.edit_c_front.text()).parent / "back2026.png"))
            if not self.edit_p_output.text():
                self.edit_p_output.setText(self.edit_c_output.text())
        self.save_settings()
        if stats.errors:
            msg += "\n\n" + self.t("errors") + "\n" + "\n".join(stats.errors[:5])
            QMessageBox.warning(self, self.t("success_title"), msg)
        else:
            QMessageBox.information(self, self.t("success_title"), msg)

    def closeEvent(self, event):
        if self.worker is not None:
            self.lbl_status.setText(self.t("busy"))
            event.ignore()
        else:
            self.save_settings()
            super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    window = StudentCardMainWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())