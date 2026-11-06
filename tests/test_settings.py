"""Settings tests only use temporary INI files, never the user's real paths."""
import os
from pathlib import Path
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import pytest

from student_card.gui import StudentCardMainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def settings(path):
    return QSettings(str(path), QSettings.IniFormat)


def test_all_paths_options_language_and_tab_survive_restart(app, tmp_path):
    file = tmp_path / "settings.ini"
    first = StudentCardMainWindow(settings=settings(file))
    values = {}
    for name in first.PATH_FIELDS:
        values[name] = str(tmp_path / f"不存在的資料 目錄/{name}")
        getattr(first, name).setText(values[name])
    first.chk_student_pdfs.setChecked(True)
    first.chk_export_3x4.setChecked(False)
    first.chk_smart_bg.setChecked(True)
    first.spin_brightness.setValue(1.0)
    first.spin_c_pdf_width.setValue(55.5)
    first.spin_p_pdf_height.setValue(90.2)
    first.toggle_language()
    first.tabs.setCurrentIndex(2)
    first.close()
    second = StudentCardMainWindow(settings=settings(file))
    assert {name: getattr(second, name).text() for name in second.PATH_FIELDS} == values
    assert second.chk_student_pdfs.isChecked() and second.chk_smart_bg.isChecked()
    assert not second.chk_export_3x4.isChecked()
    assert second.spin_brightness.value() == 1.0
    assert second.spin_c_pdf_width.value() == 55.5
    assert second.spin_p_pdf_height.value() == 90.2
    assert second.lang == "en" and second.tabs.currentIndex() == 2
    second.close()


def test_paths_auto_saved_without_close(app, tmp_path):
    file = tmp_path / "autosave.ini"
    window = StudentCardMainWindow(settings=settings(file))
    window.edit_p_back.setText("/offline-volume/back2026.png")
    QTest.qWait(500)
    assert settings(file).value("paths/edit_p_back") == "/offline-volume/back2026.png"
    window.close()


def test_persist_false_does_not_touch_provided_store(app, tmp_path):
    file = tmp_path / "unused.ini"
    window = StudentCardMainWindow(persist=False, settings=settings(file))
    window.edit_c_excel.setText("fake.xlsx")
    window.save_settings()
    window.close()
    assert not file.exists()


def test_corrupt_values_fall_back_safely(app, tmp_path):
    file = tmp_path / "corrupt.ini"
    store = settings(file)
    store.setValue("options/spin_brightness", "nan")
    store.setValue("options/spin_c_pdf_width", "garbage")
    store.setValue("ui/language", "invalid")
    store.setValue("ui/tab", "not-a-number")
    store.sync()
    window = StudentCardMainWindow(settings=settings(file))
    assert window.lang == "zh" and window.tabs.currentIndex() == 0
    assert window.spin_brightness.value() == 1.2
    assert window.spin_c_pdf_width.value() == 54
    window.close()


def test_settings_survive_fresh_python_process(app, tmp_path):
    file = tmp_path / "cross-process.ini"
    window = StudentCardMainWindow(settings=settings(file))
    window.edit_c_back.setText("/offline-volume/班別/back2026.png")
    window.chk_student_pdfs.setChecked(True)
    window.close()
    command = (
        "import sys; from PySide6.QtCore import QSettings; "
        "from PySide6.QtWidgets import QApplication; "
        "from student_card.gui import StudentCardMainWindow; "
        "app=QApplication([]); w=StudentCardMainWindow(settings=QSettings(sys.argv[1],QSettings.IniFormat)); "
        "assert w.edit_c_back.text()=='/offline-volume/班別/back2026.png'; "
        "assert w.chk_student_pdfs.isChecked(); w.close(); print('restored')"
    )
    result = subprocess.run([sys.executable, "-B", "-c", command, str(file)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "restored" in result.stdout