"""Exercise real QThreads and signal delivery without touching user settings."""
from __future__ import annotations

import os
from pathlib import Path
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest

from student_card.core import create_demo
from student_card.gui import MainWindow, STYLE


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyleSheet(STYLE)
    return instance


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    config = create_demo(tmp_path / "demo")
    config.update(output_dir=str(tmp_path / "jobs"), make_pdf=False)
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, message: errors.append((title, message)))
    view = MainWindow(config, persist=False)
    view._test_errors = errors
    view.show()
    app.processEvents()
    yield view
    if view.worker is not None:
        view.cancel()
        _wait(view)
    view.close()
    app.processEvents()


def _wait(window, timeout=20):
    deadline = time.monotonic() + timeout
    while window.worker is not None and time.monotonic() < deadline:
        QTest.qWait(10)
        # Let the Python worker thread run between Qt event-loop iterations.
        time.sleep(0.005)
    assert window.worker is None, "UI worker did not finish within acceptance timeout"


def test_validate_preview_parameter_change_and_real_background_batch(window):
    window.validate()
    assert not window.run_button.isEnabled()
    _wait(window)
    assert window.student_combo.count() == 3
    window.make_preview()
    _wait(window)
    assert window.preview_pixmap is not None
    assert not window.preview_pixmap.isNull()
    initial = window.preview_pixmap.toImage().copy()
    window.fields["brightness"].setValue(0.6)
    window.make_preview()
    _wait(window)
    assert initial != window.preview_pixmap.toImage(), "Changing brightness must alter actual preview pixels"
    window.start_job()
    assert window.cancel_button.isEnabled()
    _wait(window)
    assert not window._test_errors
    assert len(list(Path(window.last_output).rglob("*_ID.png"))) == 3
    assert window.progress_bar.value() == 100
    assert window.run_button.isEnabled()
    assert not window.cancel_button.isEnabled()
    assert window.fields["pdf_input_dir"].edit.text() == window.last_output


def test_mode_switch_changes_action_and_preview_availability(window):
    window.tabs.setCurrentIndex(1)
    assert window.mode() == "pdf"
    assert "PDF" in window.run_button.text()
    assert not window.preview_button.isEnabled()
    window.tabs.setCurrentIndex(2)
    assert window.mode() == "crop"
    assert not window.preview_button.isEnabled()
    assert window.collect_config()["photo_path"] in window.crop_photo_display.text()
    window.tabs.setCurrentIndex(0)
    assert window.mode() == "cards"
    assert window.preview_button.isEnabled()


def test_ui_cancel_finishes_worker_and_keeps_cancelled_manifest(window):
    window.start_job()
    window.cancel()
    _wait(window)
    assert window.last_output
    assert not list(Path(window.last_output).rglob("*_ID.png"))
    assert (Path(window.last_output) / "manifest.json").is_file()
    assert "停止" in window.status.text()
    assert window.run_button.isEnabled()


def test_worker_failure_restores_enabled_controls_and_actionable_error(window):
    window.fields["excel_path"].edit.setText("this-workbook-does-not-exist.xlsx")
    window.start_job()
    _wait(window)
    assert len(window._test_errors) == 1
    assert "this-workbook-does-not-exist" in window._test_errors[0][1]
    assert window.run_button.isEnabled()
    assert window.validate_button.isEnabled()
    assert not window.cancel_button.isEnabled()
