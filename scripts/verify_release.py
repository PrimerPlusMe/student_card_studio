"""Independently validate a source/frozen smoke run and its 3×4 review PDF."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
from pypdf import PdfReader
import zxingcpp


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(folder: Path) -> dict:
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    check(summary.get("passed") is True, "Smoke runner did not report success")
    check(summary.get("settings_restored") is True, "Saved paths/options did not restore")
    for mode in ("cards", "pdf", "crop"):
        result = summary[mode]
        check(result["success"] == result["total"] == 3 and result["failed"] == 0,
              f"{mode}: expected three successful fictional students")
        check(not result["errors"], f"{mode}: task reported errors")
    cards_dir = Path(summary["cards"]["output_dir"])
    cards = sorted((cards_dir / "single_cards").glob("*.png"))
    check(len(cards) == 3, "Expected three card images")
    check({p.name.split("_", 1)[0] for p in cards} == {"00001", "00002", "00003"},
          "Output IDs lost their leading zeros")
    for path in cards:
        with Image.open(path) as image:
            image.load()
            check(image.size == (649, 1033), "Wrong card dimensions")
            code = zxingcpp.read_barcode(image)
            check(code is not None and code.text == path.name.split("_", 1)[0],
                  "Code128 output did not decode to the student ID")
    pdf = Path(summary["cards"]["review_pdf"])
    check(sorted(cards_dir.glob("*.pdf")) == sorted([pdf, Path(summary["cards"]["combined_pdf"])]),
          "Unexpected top-level PDFs")
    reader = PdfReader(pdf)
    check(len(reader.pages) == 1, "Three cards should occupy one review page")
    page = reader.pages[0]
    check(abs(float(page.mediabox.width) * 25.4 / 72 - 210) < 0.1 and
          abs(float(page.mediabox.height) * 25.4 / 72 - 297) < 0.1, "Review page is not A4")
    raster = page.images[0].image.convert("RGB")
    # Verify row-major placement against each real generated card, not just page count.
    for index, path in enumerate(cards):
        with Image.open(path) as card:
            expected = card.convert("RGB").getpixel((card.width // 2, card.height // 2))
        actual = raster.getpixel((int((index + 0.5) * raster.width / 3), int(raster.height / 8)))
        check(max(abs(a - b) for a, b in zip(actual, expected)) < 35, "Review card placement differs")
    with Image.open(folder / "demo" / "back2026.png") as image:
        expected_back = image.convert("RGB").tobytes()
    for mode in ("cards", "pdf"):
        result = summary[mode]
        files = sorted(Path(result["individual_pdf_dir"]).glob("*.pdf"))
        check(len(files) == result["pdf_success"] == 3 and result["pdf_failed"] == 0,
              "Wrong number of individual PDFs")
        combined = PdfReader(result["combined_pdf"])
        check(len(combined.pages) == 6, "Combined PDF must have six pages")
        for index, (file, front) in enumerate(zip(files, cards)):
            individual = PdfReader(file)
            check(len(individual.pages) == 2, "Individual PDF must have front and back")
            with Image.open(front) as image:
                expected_front = image.convert("RGB").tobytes()
            for offset, expected in enumerate((expected_front, expected_back)):
                for page in (individual.pages[offset], combined.pages[index * 2 + offset]):
                    check(page.images[0].image.convert("RGB").tobytes() == expected,
                          "Individual/combined PDF image content or front/back order differs")
                    check(abs(float(page.mediabox.width) * 25.4 / 72 - 54) < 0.01 and
                          abs(float(page.mediabox.height) * 25.4 / 72 - 85.6) < 0.01,
                          "Wrong single-card PDF page size")
    crops = sorted(Path(summary["crop"]["output_dir"]).glob("*.jpg"))
    check(len(crops) == 3, "Expected three cropped photos")
    for path in crops:
        with Image.open(path) as image:
            image.load()
            check(image.width * 13 == image.height * 10, "Crop does not have exact 10:13 dimensions")
    with Image.open(folder / "interface.png") as image:
        check(image.width >= 780 and image.height >= 580, "Missing or invalid GUI screenshot")
    with Image.open(folder / "preview.png") as image:
        check(image.size == (649, 1033), "Invalid generated-card preview")
    return {"passed": True, "platform": summary["platform"], "detector": "yunet",
            "checks": ["3 Colab-layout cards with decoded Code128 and leading-zero IDs", "single-sided 3×4 A4 review PDF and cell order",
                       "3 exact 10:13 eClass crops", "Qt screenshot and generated-card preview",
                       "individual and combined front/back PDFs from both workflows, lossless order and page size",
                       "paths/options restored from isolated local settings"]}


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
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        if sys.platform == "win32":
            system = Path(env.get("WINDIR", "C:/Windows"))
            env["PATH"] = os.pathsep.join((str(system / "System32"), str(system)))
        else:
            env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
        for variable in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
            env.pop(variable, None)
        result = subprocess.run([str(executable), "--smoke-test", str(folder)], cwd=launch_dir,
                                env=env, capture_output=True, timeout=300)
        (folder / "executable-output.log").write_bytes(result.stdout + result.stderr)
        check(result.returncode == 0, "Packaged smoke failed; see executable-output.log/error.txt")
    report = verify(folder)
    if args.executable:
        with executable.open("rb") as stream:
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        report["exe_sha256"] = digest.hexdigest()
    (folder / "release-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())