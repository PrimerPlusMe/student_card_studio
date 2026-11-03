"""Desktop entry point, also providing a reproducible packaged smoke test."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path


def smoke_test(destination):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from student_card.core import create_demo, inspect_inputs, preview_card, run_job
    from student_card.gui import MainWindow, STYLE
    from student_card.face import FaceDetector
    from PIL import Image
    folder = Path(destination).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "error.txt").unlink(missing_ok=True)
    (folder / "summary.json").unlink(missing_ok=True)
    config = create_demo(folder / "demo")
    config["output_dir"] = str(folder / "outputs")
    report = inspect_inputs(config)
    if not report["ok"]:
        raise RuntimeError(str(report))
    preview_card(config).save(folder / "preview.png")
    cards = run_job(config, "cards")
    config["pdf_input_dir"] = cards["output_dir"]
    pdf = run_job(config, "pdf")
    crop = run_job(config, "crop")
    if any(result["success"] < 1 or result["failed"] for result in (cards, pdf, crop)):
        raise RuntimeError("End-to-end smoke test failed")
    detector = FaceDetector(config.get("model_path", ""), config.get("detector", "opencv"))
    detector.detect(Image.new("RGB", (320, 320), "white"))
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow(config, persist=False)
    window.show()
    app.processEvents()
    window.show_inspection(report)
    window.show_preview(preview_card(config))
    app.processEvents()
    window.grab().save(str(folder / "interface.png"))
    window.close()
    summary = {"passed": True, "cards": cards, "pdf": pdf, "crop": crop,
               "platform": sys.platform, "python": sys.version, "detector": config.get("detector")}
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
