"""Cross-platform Qt desktop interface. All processing runs outside the UI thread."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt, QSettings, QStandardPaths, QThread, Signal
from PySide6.QtGui import QPixmap, QDesktopServices, QCloseEvent, QFontDatabase, QFont, QIcon
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QGroupBox, QFormLayout, QScrollArea,
    QSplitter, QTabWidget, QDoubleSpinBox, QSpinBox, QCheckBox, QComboBox,
    QPlainTextEdit, QProgressBar, QMessageBox, QSizePolicy,
)

from . import __version__
from .core import default_config, inspect_inputs, preview_card, run_job, create_demo

STYLE = """
QWidget { font-family: 'Microsoft YaHei UI', 'PingFang SC', 'Arial'; font-size: 13px; color:#22334b; }
QMainWindow, QWidget#surface { background:#f2f5fa; }
QLabel#title { font-size:26px; font-weight:700; color:#142a48; }
QLabel#subtitle { color:#63738a; }
QLabel#eyebrow { color:#315fd6; font-size:11px; font-weight:700; letter-spacing:2px; }
QGroupBox { background:white; border:1px solid #e0e6ef; border-radius:10px; margin-top:17px; padding:20px 14px 12px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:16px; padding:0 7px; color:#315072; }
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox { background:#fff; border:1px solid #ced8e6; border-radius:6px; padding:7px; min-height:18px; selection-background-color:#315fd6; }
QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus { border-color:#315fd6; }
QPushButton { background:white; border:1px solid #cdd8e8; border-radius:6px; padding:9px 14px; font-weight:500; }
QPushButton:hover { background:#edf3ff; border-color:#7799eb; }
QPushButton:disabled { color:#a3afc1; background:#f3f5f8; border-color:#e1e6ee; }
QPushButton#primary { color:white; background:#315fd6; border-color:#315fd6; font-weight:600; }
QPushButton#primary:hover { background:#234dbc; }
QPushButton#danger { color:#b84646; }
QTabWidget::pane { border:0; background:#f2f5fa; }
QTabBar::tab { background:#e5ebf5; padding:11px 23px; margin-right:5px; border-radius:6px; }
QTabBar::tab:selected { color:#244eb5; background:white; font-weight:700; }
QScrollArea { border:0; background:transparent; }
QPlainTextEdit { background:#17263d; color:#d9e5f7; border:0; border-radius:8px; padding:10px; font-family:'Consolas','Menlo',monospace; font-size:12px; }
QProgressBar { border:0; background:#e0e7f2; border-radius:5px; min-height:9px; max-height:9px; }
QProgressBar::chunk { background:#315fd6; border-radius:5px; }
QLabel#preview { background:#e8edf5; border-radius:9px; color:#718198; padding:12px; }
QLabel#status { color:#566c88; }
QCheckBox { spacing:8px; padding:4px 0; }
QSplitter::handle { background:#f2f5fa; width:12px; }
"""


def configure_application(app):
    """Offscreen Qt has no native font database on Windows; use local fonts."""
    if app.property("studentCardConfigured"):
        return
    from .core import find_font
    for kind in ("chi", "eng", "id"):
        font = find_font(kind)
        if font:
            QFontDatabase.addApplicationFont(font)
    app.setApplicationName("StudentCardStudio")
    app.setOrganizationName("StudentCardStudio")
    app.setStyle("Fusion")
    families = QFontDatabase.families()
    for family in ("Microsoft YaHei UI", "PingFang SC", "Songti SC", "Arial"):
        if family in families:
            app.setFont(QFont(family, 10))
            break
    app.setStyleSheet(STYLE)
    app.setProperty("studentCardConfigured", True)


class Worker(QThread):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(int, str)

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action
        self.cancel_event = threading.Event()

    def run(self):
        try:
            self.completed.emit(self.action(self.progress.emit, self.cancel_event.is_set))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class PathField(QWidget):
    def __init__(self, kind="file", filter_text="所有文件 (*)", parent=None):
        super().__init__(parent)
        self.kind, self.filter_text = kind, filter_text
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.setMinimumWidth(160)
        self.edit.setPlaceholderText("点击右侧选择，或粘贴路径")
        layout.addWidget(self.edit, 1)
        button = QPushButton("选择")
        button.clicked.connect(self.choose)
        layout.addWidget(button)
        if kind == "photos":
            zip_button = QPushButton("ZIP")
            zip_button.setToolTip("也支持含多级目录的照片 ZIP")
            zip_button.clicked.connect(self.choose_zip)
            layout.addWidget(zip_button)

    def choose(self):
        current = self.edit.text().strip()
        if self.kind in ("folder", "photos"):
            value = QFileDialog.getExistingDirectory(self, "选择文件夹", current)
        else:
            value, _ = QFileDialog.getOpenFileName(self, "选择文件", current, self.filter_text)
        if value:
            self.edit.setText(value)

    def choose_zip(self):
        value, _ = QFileDialog.getOpenFileName(self, "选择照片 ZIP", "", "ZIP 压缩包 (*.zip)")
        if value:
            self.edit.setText(value)


class MainWindow(QMainWindow):
    def __init__(self, config=None, persist=True):
        super().__init__()
        configure_application(QApplication.instance())
        assets = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets"
        if (assets / "app.png").is_file():
            self.setWindowIcon(QIcon(str(assets / "app.png")))
        self.setWindowTitle("学生证工作室 · Student Card Studio")
        self.resize(1240, 890)
        self.setMinimumSize(1000, 720)
        self.persist = persist
        self.settings = QSettings("StudentCardStudio", "Desktop")
        self.config = default_config()
        documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        self.config["output_dir"] = str(Path(documents or str(Path.home())) / "StudentCardStudio" / "输出")
        if persist:
            try:
                saved = json.loads(self.settings.value("config", "{}"))
                self.config.update({k: v for k, v in saved.items() if k in self.config})
            except (ValueError, TypeError):
                pass
        if config:
            self.config.update(config)
        self.fields = {}
        self.worker = None
        self.last_output = ""
        self.preview_pixmap = None
        self._build()
        self.fields["photo_path"].edit.textChanged.connect(self.refresh_sources)
        self.fields["back_path"].edit.textChanged.connect(self.refresh_sources)
        self.load_fields()

    def _build(self):
        root = QWidget(objectName="surface")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(12)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(QLabel("STUDENT CARD STUDIO", objectName="eyebrow"))
        titles.addWidget(QLabel("学生证工作室", objectName="title"))
        titles.addWidget(QLabel("制作学生证 · 双面 PDF · eClass 照片裁剪    /    全程本地处理", objectName="subtitle"))
        header.addLayout(titles, 1)
        self.demo_button = QPushButton("载入演示资料")
        self.demo_button.clicked.connect(self.load_demo)
        header.addWidget(self.demo_button)
        imp = QPushButton("导入配置")
        imp.clicked.connect(self.import_config)
        header.addWidget(imp)
        exp = QPushButton("导出配置")
        exp.clicked.connect(self.export_config)
        header.addWidget(exp)
        self.config_buttons = [imp, exp]
        layout.addLayout(header)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.cards_page(), "01  制作学生证")
        self.tabs.addTab(self.pdf_page(), "02  双面 PDF")
        self.tabs.addTab(self.crop_page(), "03  eClass 裁剪")
        self.tabs.currentChanged.connect(self.mode_changed)
        split.addWidget(self.tabs)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        self.preview_title = QLabel("生成前预览", objectName="subtitle")
        right_layout.addWidget(self.preview_title)
        controls = QHBoxLayout()
        self.student_combo = QComboBox()
        self.student_combo.setMinimumContentsLength(13)
        self.student_combo.addItem("先检查资料，再选择学生", None)
        controls.addWidget(self.student_combo, 1)
        self.preview_button = QPushButton("预览")
        self.preview_button.clicked.connect(self.make_preview)
        controls.addWidget(self.preview_button)
        right_layout.addLayout(controls)
        self.preview_label = QLabel("载入底图与学生资料后\n点击“检查资料”，再生成单张预览", objectName="preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(260, 300)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        right_layout.addWidget(self.preview_label, 3)
        right_layout.addWidget(QLabel("任务记录与检查结果", objectName="subtitle"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)
        self.log.setMaximumBlockCount(4000)
        right_layout.addWidget(self.log, 1)
        split.addWidget(right)
        split.setSizes([745, 425])
        layout.addWidget(split, 1)

        output_group = QHBoxLayout()
        output_group.addWidget(QLabel("输出位置"))
        output_field = PathField("folder")
        self.fields["output_dir"] = output_field
        output_group.addWidget(output_field, 1)
        self.open_button = QPushButton("打开输出")
        self.open_button.clicked.connect(self.open_output)
        output_group.addWidget(self.open_button)
        layout.addLayout(output_group)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        footer = QHBoxLayout()
        self.status = QLabel("就绪 · 可先载入演示资料体验完整流程", objectName="status")
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        self.validate_button = QPushButton("检查资料")
        self.validate_button.clicked.connect(self.validate)
        footer.addWidget(self.validate_button)
        self.cancel_button = QPushButton("停止", objectName="danger")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        footer.addWidget(self.cancel_button)
        self.run_button = QPushButton("开始生成学生证", objectName="primary")
        self.run_button.clicked.connect(self.start_job)
        footer.addWidget(self.run_button)
        layout.addLayout(footer)
        self.log.appendPlainText(f"学生证工作室 v{__version__} 已就绪。\n演示资料为虚构绘制，首次使用请先预览。")

    def scroll_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        widget = QWidget(objectName="surface")
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(0, 3, 10, 0)
        vbox.setSpacing(8)
        scroll.setWidget(widget)
        return scroll, vbox

    def group(self, title, layout):
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setSpacing(9)
        layout.addWidget(group)
        return form

    def path(self, form, label, key, kind="file", filter_text="图片 (*.png *.jpg *.jpeg *.tif *.tiff *.bmp);;所有文件 (*)"):
        field = PathField(kind, filter_text)
        self.fields[key] = field
        form.addRow(label, field)

    def number(self, form, label, key, low, high, step=1, decimals=None):
        field = QSpinBox() if decimals is None else QDoubleSpinBox()
        field.setRange(low, high)
        field.setSingleStep(step)
        if decimals is not None:
            field.setDecimals(decimals)
        self.fields[key] = field
        form.addRow(label, field)

    def text(self, form, label, key):
        field = QLineEdit()
        self.fields[key] = field
        form.addRow(label, field)

    def check(self, form, label, key):
        field = QCheckBox(label)
        self.fields[key] = field
        form.addRow("", field)

    def cards_page(self):
        page, box = self.scroll_page()
        form = self.group("1 / 选择制作资料", box)
        self.path(form, "学生名单", "excel_path", filter_text="Excel 工作簿 (*.xlsx *.xlsm)")
        self.path(form, "学生照片", "photo_path", "photos")
        self.path(form, "正面底图", "template_path")
        self.path(form, "照片遮罩", "mask_path")
        self.path(form, "统一背面", "back_path")
        hint = QLabel("照片以学号命名，例如 000123.jpg；支持多级目录。\n遮罩白色区域显示照片，黑色区域保留底图。背面用于同时生成 PDF。")
        hint.setWordWrap(True)
        hint.setObjectName("subtitle")
        form.addRow(hint)
        form = self.group("2 / 名单列名与字体", box)
        self.text(form, "学号列名", "column_id")
        self.text(form, "英文名列名", "column_eng")
        self.text(form, "中文名列名", "column_chi")
        for label, key in [("英文字体（可选）", "font_eng_path"), ("中文字体（可选）", "font_chi_path"), ("学号字体（可选）", "font_id_path")]:
            self.path(form, label, key, filter_text="字体 (*.ttf *.ttc *.otf)")
        note = QLabel("字体留空时自动使用系统字体；与原稿完全一致需选择原来的字体文件。")
        note.setWordWrap(True)
        note.setObjectName("subtitle")
        form.addRow(note)
        form = self.group("3 / 照片、姓名与打印", box)
        detector = QComboBox()
        detector.addItem("YuNet · 鼻尖定位（推荐）", "yunet")
        detector.addItem("Haar · 基础定位", "haar")
        self.fields["detector"] = detector
        form.addRow("人脸定位", detector)
        self.number(form, "照片亮度", "brightness", 0.3, 2.0, 0.05, 2)
        self.number(form, "脸宽占照片比例", "face_ratio", 0.1, 0.8, 0.01, 2)
        self.number(form, "照片垂直偏移", "photo_offset_y", -300, 300)
        self.number(form, "英文字号", "eng_font_size", 8, 150)
        self.number(form, "中文字号", "chi_font_size", 8, 150)
        self.number(form, "学号字号", "id_font_size", 8, 150)
        self.number(form, "成品宽度 / mm", "pdf_width_mm", 20, 300, 0.1, 1)
        self.number(form, "成品高度 / mm", "pdf_height_mm", 20, 300, 0.1, 1)
        self.check(form, "同时生成每人及全班双面 PDF（需背面）", "make_pdf")
        self.check(form, "完成后打包 ZIP", "make_zip")
        advanced = QGroupBox("高级排版参数 · 展开调整")
        advanced.setCheckable(True)
        advanced.setChecked(False)
        adv_content = QWidget()
        af = QFormLayout(adv_content)
        for label, key in [("参考底图宽度", "reference_width"), ("参考底图高度", "reference_height"), ("文字中心 X", "center_x"), ("照片左上 X", "photo_x"), ("照片左上 Y", "photo_y"), ("照片半径", "face_radius"), ("单行英文 Y", "eng_only_y"), ("双行英文 Y", "eng_dual_y"), ("中文 Y", "chi_dual_y"), ("条码宽度", "barcode_width"), ("条码高度", "barcode_height"), ("条码底部 Y", "barcode_bottom_y"), ("学号顶部 Y", "id_text_top_y")]:
            self.number(af, label, key, 1, 20000)
        av = QVBoxLayout(advanced)
        av.addWidget(adv_content)
        adv_content.setVisible(False)
        advanced.toggled.connect(adv_content.setVisible)
        box.addWidget(advanced)
        box.addStretch()
        return page

    def pdf_page(self):
        page, box = self.scroll_page()
        form = self.group("将现有学生证正面合并为双面 PDF", box)
        self.path(form, "正面 PNG 文件夹", "pdf_input_dir", "folder")
        info = QLabel("使用“制作学生证”页面选择的统一背面和成品毫米尺寸。\n按文件名排序，每人依次为正面、背面；另生成全班合并文件。\n可直接选择某次任务的输出目录，程序会递归查找 PNG。")
        info.setWordWrap(True)
        info.setObjectName("subtitle")
        form.addRow(info)
        self.pdf_back_display = QLabel()
        self.pdf_back_display.setWordWrap(True)
        form.addRow("当前背面", self.pdf_back_display)
        choose_back = QPushButton("选择统一背面图片")
        choose_back.clicked.connect(lambda: self.fields["back_path"].choose())
        form.addRow("", choose_back)
        self.pdf_size_display = QLabel()
        form.addRow("当前成品尺寸", self.pdf_size_display)
        box.addStretch()
        return page

    def crop_page(self):
        page, box = self.scroll_page()
        form = self.group("批量裁剪为宽 : 高 = 10 : 13", box)
        info = QLabel("使用“制作学生证”页面选择的照片文件夹或 ZIP。\n按人脸定位保留尽可能多的上半身；保留原照片，裁剪结果另存。\n未检测到人脸或检测到多人时，会在明细中标记人工复核。")
        info.setWordWrap(True)
        info.setObjectName("subtitle")
        form.addRow(info)
        self.crop_photo_display = QLabel()
        self.crop_photo_display.setWordWrap(True)
        form.addRow("当前照片", self.crop_photo_display)
        choose = QPushButton("选择照片文件夹")
        choose.clicked.connect(lambda: self.fields["photo_path"].choose())
        choose_zip = QPushButton("选择照片 ZIP")
        choose_zip.clicked.connect(lambda: self.fields["photo_path"].choose_zip())
        form.addRow(choose, choose_zip)
        box.addStretch()
        return page

    def mode(self):
        return ("cards", "pdf", "crop")[self.tabs.currentIndex()]

    def mode_changed(self, *_):
        if not hasattr(self, "run_button"):
            return
        self.run_button.setText(("开始生成学生证", "开始生成 PDF", "开始裁剪照片")[self.tabs.currentIndex()])
        self.refresh_sources()
        is_cards = self.mode() == "cards"
        self.preview_button.setEnabled(is_cards and self.worker is None)
        self.student_combo.setEnabled(is_cards and self.worker is None)

    def refresh_sources(self, *_):
        config = self.collect_config()
        self.pdf_back_display.setText(config.get("back_path") or "尚未选择")
        self.pdf_size_display.setText(f'{config["pdf_width_mm"]:g} × {config["pdf_height_mm"]:g} mm')
        self.crop_photo_display.setText(config.get("photo_path") or "尚未选择")

    def load_fields(self):
        for key, field in self.fields.items():
            value = self.config.get(key)
            if isinstance(field, PathField):
                field.edit.setText(str(value or ""))
            elif isinstance(field, QLineEdit):
                field.setText(str(value or ""))
            elif isinstance(field, QCheckBox):
                field.setChecked(bool(value))
            elif isinstance(field, QComboBox):
                field.setCurrentIndex(max(0, field.findData("haar" if value == "opencv" else value)))
            else:
                field.setValue(value)
        self.mode_changed()

    def collect_config(self):
        config = dict(self.config)
        for key, field in self.fields.items():
            if isinstance(field, PathField):
                config[key] = field.edit.text().strip().strip('"')
            elif isinstance(field, QLineEdit):
                config[key] = field.text().strip()
            elif isinstance(field, QCheckBox):
                config[key] = field.isChecked()
            elif isinstance(field, QComboBox):
                config[key] = field.currentData()
            else:
                config[key] = field.value()
        return config

    def save_settings(self):
        self.config = self.collect_config()
        if self.persist:
            self.settings.setValue("config", json.dumps(self.config, ensure_ascii=False))

    def busy(self, value):
        for widget in [self.tabs, self.run_button, self.validate_button, self.demo_button, self.preview_button, self.student_combo, *self.config_buttons]:
            widget.setEnabled(not value)
        self.fields["output_dir"].setEnabled(not value)
        self.cancel_button.setEnabled(value)
        if not value:
            self.mode_changed()

    def launch(self, title, action, completed):
        if self.worker is not None:
            return
        self.save_settings()
        self.progress_bar.setValue(0)
        self.status.setText(title)
        self.log.appendPlainText("\n" + title)
        worker = Worker(action, self)
        self.worker = worker
        self.busy(True)
        worker.progress.connect(self.on_progress)
        worker.completed.connect(completed)
        worker.failed.connect(self.on_error)
        worker.finished.connect(self.worker_finished)
        worker.start()

    def worker_finished(self):
        worker = self.worker
        self.worker = None
        self.busy(False)
        if worker:
            worker.deleteLater()

    def on_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self.status.setText(message)
        self.log.appendPlainText(message)

    def on_error(self, message):
        self.status.setText("处理失败，请查看任务记录")
        self.log.appendPlainText("错误：" + message)
        QMessageBox.warning(self, "无法完成", message)

    def validate(self):
        config, mode = self.collect_config(), self.mode()
        self.launch("正在检查输入资料…", lambda p, c: inspect_inputs(config, mode), self.show_inspection)

    def show_inspection(self, result):
        self.progress_bar.setValue(100)
        self.log.appendPlainText(f'发现照片：{result.get("photo_count", 0)}；名单记录：{len(result.get("students", []))}')
        for item in result.get("errors", []):
            self.log.appendPlainText("错误 · " + item)
        for item in result.get("warnings", []):
            self.log.appendPlainText("提示 · " + item)
        students = result.get("students", [])
        if self.mode() == "cards":
            self.student_combo.clear()
            for student in students:
                self.student_combo.addItem(f'{student["student_id"]} · {student["english_name"]}', student["student_id"])
                if student.get("issues"):
                    self.log.appendPlainText(f'{student["student_id"]} · {"；".join(student["issues"])}')
        self.status.setText("检查通过，请预览后生成" if result.get("ok") else "检查未通过，请按错误提示修正")

    def make_preview(self):
        config = self.collect_config()
        sid = self.student_combo.currentData()
        self.launch("正在生成单张预览…", lambda p, c: preview_card(config, sid), self.show_preview)

    def show_preview(self, pil_image):
        self.preview_pixmap = QPixmap.fromImage(ImageQt(pil_image.convert("RGBA")))
        self.update_preview()
        self.progress_bar.setValue(100)
        notes = pil_image.info.get("review_notes", [])
        if notes:
            self.status.setText("预览已更新 · 人脸定位需人工复核，详见任务记录")
            for note in notes:
                self.log.appendPlainText("预览提示 · " + note)
        else:
            self.status.setText("预览已更新 · 可调整参数后再次预览")

    def update_preview(self):
        if self.preview_pixmap:
            size = self.preview_label.size()
            self.preview_label.setPixmap(self.preview_pixmap.scaled(max(1, size.width() - 26), max(1, size.height() - 26), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "preview_label"):
            self.update_preview()

    def start_job(self):
        config, mode = self.collect_config(), self.mode()
        self.launch("正在创建任务并检查资料…", lambda p, c: run_job(config, mode, p, c), self.job_done)

    def job_done(self, result):
        self.last_output = result.get("output_dir", "")
        self.progress_bar.setValue(100 if not result.get("cancelled") else self.progress_bar.value())
        label = "已停止" if result.get("cancelled") else "已完成"
        summary = f'{label} · 成功 {result.get("success",0)} / 失败 {result.get("failed",0)} / 跳过 {result.get("skipped",0)} / 待复核 {result.get("review",0)}'
        self.status.setText(summary)
        self.log.appendPlainText(summary + "\n输出：" + self.last_output + "\n详细原因请查看输出目录内的 CSV 和 manifest.json。")
        if self.mode() == "cards" and self.last_output:
            # Core output subfolder is discovered by PDF job's recursive PNG search.
            self.fields["pdf_input_dir"].edit.setText(self.last_output)

    def cancel(self):
        if self.worker:
            self.worker.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("正在停止，当前文件完成后保留已生成结果…")

    def load_demo(self):
        data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        destination = Path(data or str(Path.home() / ".student-card-studio")) / "demo"
        output = self.collect_config()["output_dir"]
        self.launch("正在准备虚构演示资料…", lambda p, c: create_demo(destination), lambda result: self.demo_done(result, output))

    def demo_done(self, result, output):
        self.config.update(result)
        self.config["output_dir"] = output
        self.load_fields()
        self.tabs.setCurrentIndex(0)
        self.status.setText("演示资料已载入，请点击“检查资料”和“预览”")
        self.log.appendPlainText("演示使用绘制人像，不代表真实人脸检测效果；人工复核提示属于预期结果。")
        self.progress_bar.setValue(100)

    def open_output(self):
        target = Path(self.last_output or self.collect_config()["output_dir"])
        target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve())))

    def import_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入配置", "", "JSON 配置 (*.json)")
        if not path:
            return
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            if not isinstance(value, dict):
                raise ValueError("配置应为 JSON 对象")
            defaults = default_config()
            for key, val in value.items():
                if key not in defaults:
                    continue
                expected = defaults[key]
                if isinstance(expected, bool) and not isinstance(val, bool):
                    raise ValueError(f"{key} 应为布尔值")
                if isinstance(expected, (int, float)) and not isinstance(expected, bool) and (isinstance(val, bool) or not isinstance(val, (int, float))):
                    raise ValueError(f"{key} 应为数值")
                if isinstance(expected, str) and not isinstance(val, str):
                    raise ValueError(f"{key} 应为字符串")
            self.config.update({k: v for k, v in value.items() if k in defaults})
            self.load_fields()
            self.save_settings()
            self.status.setText("配置已导入，跨系统使用时请重新选择文件路径")
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "导入失败", str(exc))

    def export_config(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出配置", "学生证配置.json", "JSON 配置 (*.json)")
        if path:
            try:
                Path(path).write_text(json.dumps(self.collect_config(), ensure_ascii=False, indent=2), encoding="utf-8")
                self.status.setText("配置已导出")
            except OSError as exc:
                QMessageBox.warning(self, "导出失败", str(exc))

    def closeEvent(self, event: QCloseEvent):
        if self.worker is not None:
            self.cancel()
            self.status.setText("任务正在停止，停止后可关闭窗口")
            event.ignore()
            return
        self.save_settings()
        event.accept()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    configure_application(app)
    window = MainWindow()
    window.show()
    return app.exec()
