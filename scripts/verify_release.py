"""Independently verify files produced by a source or packaged smoke test.

Usage:
  python scripts/verify_release.py --smoke-dir validation/windows-exe
  python scripts/verify_release.py --executable dist/StudentCardStudio.exe --smoke-dir validation/windows-exe

The executable is launched from a separate working directory with Python omitted
from PATH. No real students or original assets are required.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from PIL import Image
from pypdf import PdfReader
import zxingcpp


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(folder: Path) -> dict:
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    check(summary.get("passed") is True, "Smoke runner did not report success")
    outputs = {mode: Path(summary[mode]["output_dir"]) for mode in ("cards", "pdf", "crop")}
    checks = []
    for mode, output in outputs.items():
        result = summary[mode]
        check(result["success"] == 3, f"{mode}: expected three synthetic students")
        check(result["failed"] == result["skipped"] == 0, f"{mode}: unexpected failures/skips")
        check(not result["cancelled"], f"{mode}: unexpectedly cancelled")
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        check(manifest["summary"] == result, f"{mode}: manifest totals disagree with smoke summary")
        with (output / "processing_report.csv").open(encoding="utf-8-sig", newline="") as handle:
            records = list(csv.DictReader(handle))
        check(len(records) == 3, f"{mode}: incorrect report row count")
        for record in records:
            check(record["status"] in ("success", "review"), f"{mode}: bad status {record['status']}")
            check((output / record["output"]).is_file(), f"{mode}: reported file missing")
        with zipfile.ZipFile(output / "results.zip") as archive:
            check(archive.testzip() is None, f"{mode}: damaged output ZIP")
            check(not any(".working" in name for name in archive.namelist()), f"{mode}: temporary file leaked")
        checks.append(f"{mode}: three records, consistent manifest/report, complete ZIP")

    cards = sorted(outputs["cards"].rglob("*_ID.png"))
    check(len(cards) == 3, "Expected exactly three student-card PNGs")
    ids = set()
    for card in cards:
        with Image.open(card) as image:
            codes = zxingcpp.read_barcodes(image.convert("RGB"))
        check(len(codes) == 1, f"Unreadable or ambiguous barcode: {card.name}")
        check(codes[0].format == zxingcpp.BarcodeFormat.Code128, f"Wrong barcode format: {card.name}")
        ids.add(codes[0].text)
    check(ids == {"00001", "00002", "00003"}, "Barcode payloads lost leading zeros")
    checks.append("Three Code128 barcodes independently decoded with exact leading-zero IDs")

    for mode in ("cards", "pdf"):
        pdfs = list(outputs[mode].rglob("*.pdf"))
        check(len(pdfs) == 4, f"{mode}: expected three individual PDFs and one combined PDF")
        page_counts = []
        for path in pdfs:
            reader = PdfReader(path)
            page_counts.append(len(reader.pages))
            for index, page in enumerate(reader.pages):
                width_mm = float(page.mediabox.width) * 25.4 / 72
                height_mm = float(page.mediabox.height) * 25.4 / 72
                check(abs(width_mm - 54.0) < 0.02 and abs(height_mm - 85.6) < 0.02, f"{path.name}: wrong print dimensions")
                image = page.images[0].image.convert("RGB")
                color = image.getpixel((int(image.width * 0.02), int(image.height * 0.5)))
                expected = (23, 63, 99) if index % 2 else (255, 255, 255)
                check(color == expected, f"{path.name}: wrong front/back page sequence")
        check(sorted(page_counts) == [2, 2, 2, 6], f"{mode}: unexpected PDF page counts")
    checks.append("Both PDF workflows: 2/2/2/6 pages, front/back order, 54 × 85.6 mm")

    cropped = list(outputs["crop"].rglob("*.jpg"))
    check(len(cropped) == 3, "Expected three eClass photos")
    for path in cropped:
        with Image.open(path) as image:
            check(image.width * 13 == image.height * 10, f"Wrong 10:13 ratio: {path.name}")
    checks.append("Three eClass photos have exact 10:13 dimensions")
    with Image.open(folder / "interface.png") as screenshot:
        check(screenshot.width >= 1000 and screenshot.height >= 700, "UI screenshot is missing or too small")
    with Image.open(folder / "preview.png") as preview:
        check(preview.size == (648, 1050), "Preview dimensions do not match the demo template")
    checks.append("Qt interface screenshot and student-card preview produced")
    return {"passed": True, "platform": summary["platform"], "detector": summary.get("detector"), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-dir", type=Path, required=True)
    parser.add_argument("--executable", type=Path)
    args = parser.parse_args()
    folder = args.smoke_dir.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if args.executable:
        executable = args.executable.resolve()
        launch_dir = folder / "independent-working-directory"
        launch_dir.mkdir(exist_ok=True)
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        if sys.platform == "win32":
            system = Path(env.get("WINDIR", "C:/Windows"))
            env["PATH"] = os.pathsep.join((str(system / "System32"), str(system)))
        else:
            env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
        for variable in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
            env.pop(variable, None)
        completed = subprocess.run([str(executable), "--smoke-test", str(folder)], cwd=launch_dir, env=env, capture_output=True, timeout=240)
        (folder / "executable-output.log").write_bytes(completed.stdout + completed.stderr)
        check(completed.returncode == 0, f"Packaged smoke test failed with code {completed.returncode}; see executable-output.log/error.txt")
    report = verify(folder)
    (folder / "release-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
