"""Desktop entry point, also providing a reproducible packaged smoke test."""
from __future__ import annotations
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path


def smoke_test(destination):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QSettings
    from student_card.core import batch_generate_cards, batch_crop_eclass_only, batch_generate_pdfs
    from student_card.demo import create_demo
    from student_card.gui import StudentCardMainWindow
    from PIL import Image
    folder = Path(destination).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "error.txt").unlink(missing_ok=True)
    (folder / "summary.json").unlink(missing_ok=True)
    config = create_demo(folder / "demo")
    config["output_dir"] = str(folder / "outputs")
    back_path = str(Path(config["front_template"]).parent / "back2026.png")
    cards = batch_generate_cards(**config, back_path=back_path, export_student_pdfs=True)
    pdf = batch_generate_pdfs(str(Path(cards.output_dir) / "single_cards"), back_path, str(folder / "outputs"))
    crop = batch_crop_eclass_only(config["photos_dir"], str(folder / "outputs"))
    if any(result.success != 3 or result.failed or result.errors for result in (cards, pdf, crop)):
        raise RuntimeError("End-to-end smoke test failed")
    if not cards.review_pdf or not Path(cards.review_pdf).is_file():
        raise RuntimeError("3×4 review PDF was not generated")
    with Image.open(next((Path(cards.output_dir) / "single_cards").glob("*.png"))) as card:
        card.save(folder / "preview.png")
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    settings_path = str(folder / "smoke-settings.ini")
    window = StudentCardMainWindow(settings=QSettings(settings_path, QSettings.IniFormat))
    for edit, value in ((window.edit_c_excel, config["excel_path"]),
                        (window.edit_c_photos, config["photos_dir"]),
                        (window.edit_c_front, config["front_template"]),
                        (window.edit_c_mask, config["mask_path"]),
                        (window.edit_c_back, back_path),
                        (window.edit_c_output, config["output_dir"])):
        edit.setText(value)
    window.chk_student_pdfs.setChecked(True)
    window.edit_p_fronts.setText(str(Path(cards.output_dir) / "single_cards"))
    window.edit_p_back.setText(back_path)
    window.edit_p_output.setText(str(folder / "outputs"))
    window.show()
    app.processEvents()
    window.grab().save(str(folder / "interface.png"))
    saved_paths = {name: getattr(window, name).text() for name in window.PATH_FIELDS}
    window.close()
    restored = StudentCardMainWindow(settings=QSettings(settings_path, QSettings.IniFormat))
    settings_restored = all(getattr(restored, name).text() == value for name, value in saved_paths.items())
    settings_restored = settings_restored and restored.chk_student_pdfs.isChecked()
    restored.close()
    if not settings_restored:
        raise RuntimeError("Settings did not survive window recreation")
    summary = {"passed": True, "cards": asdict(cards), "pdf": asdict(pdf), "crop": asdict(crop),
               "settings_restored": settings_restored,
               "platform": sys.platform, "python": sys.version, "detector": "yunet"}
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        index = sys.argv.index("--smoke-test")
        destination = sys.argv[index + 1] if len(sys.argv) > index + 1 else "smoke-test-output"
        try:
            raise SystemExit(smoke_test(destination))
        except Exception:
            import traceback
            Path(destination).mkdir(parents=True, exist_ok=True)
            (Path(destination) / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise SystemExit(1)
    else:
        from student_card.gui import main
        raise SystemExit(main())
