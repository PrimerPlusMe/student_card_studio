"""Real QThread and signal-delivery checks for the current bilingual UI."""
import os
from pathlib import Path
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest

from student_card import gui
from student_card.core import ProcessStats
from student_card.demo import create_demo


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait(window, timeout=20):
    deadline = time.monotonic() + timeout
    while window.worker is not None and time.monotonic() < deadline:
        QTest.qWait(10)
        time.sleep(0.005)
    assert window.worker is None, "Background task did not finish"


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    messages = []
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, kind, lambda parent, title, text, kind=kind: messages.append((kind, text)))
    view = gui.StudentCardMainWindow(persist=False)
    config = create_demo(tmp_path / "demo")
    for edit, key in ((view.edit_c_excel, "excel_path"), (view.edit_c_photos, "photos_dir"),
                      (view.edit_c_front, "front_template"), (view.edit_c_mask, "mask_path"),
                      (view.edit_c_output, "output_dir")):
        edit.setText(config[key])
    view.edit_cr_src.setText(config["photos_dir"])
    view.edit_cr_out.setText(config["output_dir"])
    view.messages = messages
    view.show()
    app.processEvents()
    yield view
    if view.worker is not None:
        wait(view)
    view.close()
    app.processEvents()


def test_bilingual_ui_without_removed_options(window):
    assert window.tabs.count() == 3
    assert not hasattr(window, "chk_export_pdf")
    assert hasattr(window, "edit_c_back")
    window.toggle_language()
    assert window.windowTitle() == "Student Card Studio"
    assert "3x4" in window.chk_export_3x4.text()
    window.toggle_language()
    assert "學生證" in window.windowTitle()


@pytest.mark.parametrize("pdf", [False, True])
def test_real_card_worker_and_accurate_completion_message(window, pdf):
    window.chk_export_3x4.setChecked(pdf)
    window._start_cards()
    assert not window.btn_gen_cards.isEnabled()
    assert not window.btn_gen_crop.isEnabled()
    wait(window)
    assert window.last_stats.success == 3
    assert window.progress_bar.value() == 100
    assert window.btn_gen_cards.isEnabled() and window.btn_gen_crop.isEnabled()
    assert len(list((Path(window.last_output) / "single_cards").glob("*.png"))) == 3
    text = window.messages[-1][1]
    assert ("student_cards_review_3x4.pdf" in text) == pdf
    assert "student_cards_print_A4" not in text


def test_real_crop_worker(window):
    window._start_crop()
    wait(window)
    assert window.last_stats.success == 3
    assert len(list(Path(window.last_output).glob("*.jpg"))) == 3


def test_failure_restores_controls_and_allows_retry(window):
    valid = window.edit_c_excel.text()
    window.edit_c_excel.setText("missing-students.xlsx")
    window._start_cards()
    wait(window)
    assert window.messages[-1][0] == "critical"
    assert "missing-students.xlsx" in window.messages[-1][1]
    assert window.tabs.isEnabled() and window.btn_gen_cards.isEnabled()
    window.edit_c_excel.setText(valid)
    window.chk_export_3x4.setChecked(False)
    window._start_cards()
    wait(window)
    assert window.last_stats.success == 3


def test_prevent_overlap_and_closing_while_running(window, monkeypatch):
    gate = threading.Event()
    calls = []
    def slow(**kwargs):
        calls.append(kwargs)
        gate.wait(5)
        return ProcessStats(total=1, success=1, output_dir="test-output")
    monkeypatch.setattr(gui, "batch_generate_cards", slow)
    window._start_cards()
    worker = window.worker
    try:
        window._start_crop()
        window._start_cards()
        assert window.worker is worker
        assert not window.close()
        assert window.isVisible()
    finally:
        gate.set()
        wait(window)
    assert len(calls) == 1


def test_pdf_error_uses_warning_not_success(window, monkeypatch):
    monkeypatch.setattr(gui, "batch_generate_cards", lambda **kwargs: ProcessStats(
        total=1, success=1, output_dir="test-output", errors=["Review PDF export failed"]))
    window._start_cards()
    wait(window)
    assert window.messages[-1][0] == "warning"
    assert "student_cards_review_3x4.pdf" not in window.messages[-1][1]


def test_unknown_worker_task_is_explicit_error():
    worker = gui.WorkerThread("unknown", {})
    worker.run()
    assert "Unknown task" in worker.error


def test_missing_mask_restores_ui_without_generating_wrong_cards(window):
    window.edit_c_mask.setText("missing-portrait-mask.png")
    window._start_cards()
    wait(window)
    assert window.messages[-1][0] == "critical"
    assert "missing-portrait-mask.png" in window.messages[-1][1]
    assert window.tabs.isEnabled() and window.last_stats is None


def test_ui_passes_all_colab_resources_and_brightness(window, monkeypatch):
    captured = {}
    def capture(**kwargs):
        captured.update(kwargs)
        return ProcessStats(total=1, success=1, output_dir="test-output")
    monkeypatch.setattr(gui, "batch_generate_cards", capture)
    window.edit_c_font_eng.setText("english.ttf")
    window.edit_c_font_chi.setText("chinese.ttf")
    window.edit_c_font_id.setText("id.ttf")
    window.spin_brightness.setValue(1.35)
    window._start_cards()
    wait(window)
    assert captured["brightness"] == 1.35
    assert captured["mask_path"] == window.edit_c_mask.text()
    assert [captured[key] for key in ("font_eng_path", "font_chi_path", "font_id_path")] == [
        "english.ttf", "chinese.ttf", "id.ttf"]


def test_card_pdf_options_and_pdf_only_real_worker(window):
    back = str(Path(window.edit_c_front.text()).parent / "back2026.png")
    window.edit_c_back.setText(back)
    window.chk_student_pdfs.setChecked(True)
    window._start_cards()
    assert not window.btn_gen_pdf.isEnabled()
    wait(window)
    assert window.last_stats.pdf_success == 3
    assert Path(window.last_stats.combined_pdf).is_file()
    assert "All_Students_Combined.pdf" in window.messages[-1][1]
    assert window.edit_p_back.text() == back
    assert Path(window.edit_p_fronts.text()).name == "single_cards"
    window._start_pdf()
    wait(window)
    assert window.last_stats.success == window.last_stats.pdf_success == 3
    assert Path(window.last_stats.combined_pdf).is_file()
    assert window.btn_gen_pdf.isEnabled()


def test_pdf_only_failure_restores_all_buttons(window):
    window.edit_p_fronts.setText(window.edit_c_photos.text())
    window.edit_p_back.setText("missing-back.png")
    window.edit_p_output.setText(window.edit_c_output.text())
    window._start_pdf()
    wait(window)
    assert window.messages[-1][0] == "critical"
    assert all(button.isEnabled() for button in (
        window.btn_gen_pdf, window.btn_gen_cards, window.btn_gen_crop))