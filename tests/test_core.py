"""Acceptance checks against artifacts, using only synthetic student records."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

import pytest
from openpyxl import load_workbook
from PIL import Image, ImageChops
from pypdf import PdfReader
import zxingcpp

from student_card import core


def _hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file() and "output" not in path.parts
    }


def _config(tmp_path: Path) -> dict:
    config = core.create_demo(tmp_path / "demo")
    config["output_dir"] = str(tmp_path / "jobs")
    return config


def _messages(inspection: dict) -> str:
    return json.dumps(inspection, ensure_ascii=False)


def _pngs(output: Path) -> list[Path]:
    return sorted(output.rglob("*_ID.png"))


def _pdfs(output: Path) -> list[Path]:
    return sorted(output.rglob("*.pdf"))


def _decode(path: Path) -> str:
    with Image.open(path) as image:
        decoded = zxingcpp.read_barcodes(image.convert("RGB"))
    assert len(decoded) == 1, f"Expected exactly one readable barcode in {path}"
    assert decoded[0].format == zxingcpp.BarcodeFormat.Code128
    return decoded[0].text


@pytest.fixture(scope="module")
def completed_cards(tmp_path_factory):
    folder = tmp_path_factory.mktemp("complete_cards")
    config = _config(folder)
    before = _hashes(folder / "demo")
    messages = []
    result = core.run_job(config, "cards", progress=lambda value, msg: messages.append((value, msg)))
    return folder, config, before, result, messages


def test_demo_preflight_and_leading_zero_ids(tmp_path):
    config = _config(tmp_path)
    inspection = core.inspect_inputs(config)
    assert inspection["ok"], inspection
    assert inspection["photo_count"] == 3
    assert [row["student_id"] for row in inspection["students"]] == ["00001", "00002", "00003"]
    assert all(Path(row["photo"]).suffix.lower() == ".jpg" for row in inspection["students"])


def test_cards_success_count_and_progress(completed_cards):
    _, _, _, result, messages = completed_cards
    assert result["success"] == 3
    assert result["failed"] == result["skipped"] == 0
    assert result["cancelled"] is False
    assert len(_pngs(Path(result["output_dir"]))) == 3
    assert messages and messages[-1][0] == 100
    assert all(0 <= percent <= 100 for percent, _ in messages)


def test_generated_code128_is_machine_readable(completed_cards):
    _, _, _, result, _ = completed_cards
    assert {_decode(path) for path in _pngs(Path(result["output_dir"]))} == {"00001", "00002", "00003"}


def test_pdf_page_count_actual_size_and_front_back_sequence(completed_cards):
    _, _, _, result, _ = completed_cards
    pdfs = _pdfs(Path(result["output_dir"]))
    assert len(pdfs) == 4
    readers = [(path, PdfReader(path)) for path in pdfs]
    assert sorted(len(reader.pages) for _, reader in readers) == [2, 2, 2, 6]
    for _, reader in readers:
        for index, page in enumerate(reader.pages):
            assert float(page.mediabox.width) * 25.4 / 72 == pytest.approx(54.0, abs=0.02)
            assert float(page.mediabox.height) * 25.4 / 72 == pytest.approx(85.6, abs=0.02)
            image = page.images[0].image.convert("RGB")
            point = image.getpixel((int(image.width * 0.02), int(image.height * 0.5)))
            if index % 2:
                assert point == (23, 63, 99), "Odd pages must show the shared blue back"
            else:
                assert point == (255, 255, 255), "Even pages must show the student front"


def test_reports_zip_and_inputs_preserved(completed_cards):
    folder, _, before, result, _ = completed_cards
    output = Path(result["output_dir"])
    assert _hashes(folder / "demo") == before
    manifests = list(output.rglob("manifest.json"))
    reports = list(output.rglob("processing_report.csv"))
    assert len(manifests) == len(reports) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["summary"] == result
    assert manifest["mode"] == "cards"
    report = reports[0].read_bytes()
    assert report.startswith(b"\xef\xbb\xbf"), "CSV should open correctly in Chinese Excel"
    rows = list(csv.DictReader(report.decode("utf-8-sig").splitlines()))
    assert len(rows) == 3
    assert {row.get("student_id", row.get("学号", "")) for row in rows} == {"00001", "00002", "00003"}
    assert sum(row["status"] in {"success", "review"} for row in rows) == result["success"]
    assert sum(row["status"] == "review" for row in rows) == result["review"]
    assert all((output / row["output"]).is_file() for row in rows)
    archives = list(output.rglob("*.zip"))
    if not archives:
        archives = list(output.parent.glob(output.name + "*.zip"))
    assert len(archives) == 1
    with zipfile.ZipFile(archives[0]) as archive:
        names = archive.namelist()
        assert len([name for name in names if name.endswith("_ID.png")]) == 3
        assert not any(name.lower().endswith((".xlsx", ".ttf", ".ttc")) for name in names)


def test_preview_uses_same_pixels_as_batch(completed_cards):
    _, config, _, result, _ = completed_cards
    preview = core.preview_card(config, "00001").convert("RGB")
    card = next(path for path in _pngs(Path(result["output_dir"])) if path.name.startswith("00001"))
    with Image.open(card) as image:
        assert ImageChops.difference(preview, image.convert("RGB")).getbbox() is None


def test_crop_outputs_have_ten_to_thirteen_ratio(tmp_path):
    config = _config(tmp_path)
    result = core.run_job(config, "crop")
    assert result["success"] == 3
    images = [path for path in Path(result["output_dir"]).rglob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    assert len(images) == 3
    for path in images:
        with Image.open(path) as image:
            assert abs(image.width * 13 - image.height * 10) <= 13


def test_pdf_only_uses_existing_fronts(completed_cards, tmp_path):
    _, original, _, result, _ = completed_cards
    config = dict(original)
    config["pdf_input_dir"] = str(_pngs(Path(result["output_dir"]))[0].parent)
    config["output_dir"] = str(tmp_path / "pdf_only")
    config["excel_path"] = config["photo_path"] = config["template_path"] = config["mask_path"] = ""
    inspection = core.inspect_inputs(config, "pdf")
    assert inspection["ok"], inspection
    generated = core.run_job(config, "pdf")
    assert generated["success"] == 3
    assert len(_pdfs(Path(generated["output_dir"]))) == 4


def test_repeated_job_does_not_overwrite_existing_output(tmp_path):
    config = _config(tmp_path)
    config["make_pdf"] = False
    first = core.run_job(config, "cards")
    before = {str(path): path.read_bytes() for path in Path(first["output_dir"]).rglob("*") if path.is_file()}
    second = core.run_job(config, "cards")
    assert first["output_dir"] != second["output_dir"]
    assert all(Path(path).read_bytes() == content for path, content in before.items())


def test_missing_photo_is_reported_and_not_counted_as_success(tmp_path):
    config = _config(tmp_path)
    (Path(config["photo_path"]) / "00002.jpg").unlink()
    inspection = core.inspect_inputs(config)
    target = next(row for row in inspection["students"] if row["student_id"] == "00002")
    assert target["issues"]
    config["make_pdf"] = False
    result = core.run_job(config, "cards")
    assert result["success"] == 2
    assert result["failed"] + result["skipped"] == 1
    assert len(_pngs(Path(result["output_dir"]))) == 2


def test_corrupt_photo_cannot_generate_a_blank_success_card(tmp_path):
    config = _config(tmp_path)
    (Path(config["photo_path"]) / "00002.jpg").write_bytes(b"not an image")
    config["make_pdf"] = False
    result = core.run_job(config, "cards")
    assert result["success"] == 2
    assert result["failed"] + result["skipped"] == 1
    assert not any(path.name.startswith("00002") for path in _pngs(Path(result["output_dir"])))


def test_duplicate_student_id_cannot_silently_overwrite(tmp_path):
    config = _config(tmp_path)
    workbook = load_workbook(config["excel_path"])
    workbook.active.append(["00001", "DUPLICATE", "重复"])
    workbook.save(config["excel_path"])
    inspection = core.inspect_inputs(config)
    duplicate_rows = [row for row in inspection["students"] if row["student_id"] == "00001"]
    assert len(duplicate_rows) == 2
    assert all(row["issues"] for row in duplicate_rows)
    config["make_pdf"] = False
    result = core.run_job(config)
    assert result["success"] == 2
    assert result["skipped"] == 2
    assert not any(path.name.startswith("00001") for path in _pngs(Path(result["output_dir"])))


def test_multiple_photos_for_one_student_are_flagged(tmp_path):
    config = _config(tmp_path)
    shutil.copyfile(Path(config["photo_path"]) / "00001.jpg", Path(config["photo_path"]) / "00001.png")
    inspection = core.inspect_inputs(config)
    target = next(row for row in inspection["students"] if row["student_id"] == "00001")
    assert target["issues"], "Ambiguous photo choices need an explicit issue"


def test_nested_zip_photo_input(tmp_path):
    config = _config(tmp_path)
    archive_path = tmp_path / "photos.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in Path(config["photo_path"]).glob("*.jpg"):
            archive.write(path, "class_1/photos/" + path.name)
        archive.writestr("__MACOSX/._00001.jpg", b"ignored metadata")
    config["photo_path"] = str(archive_path)
    config["make_pdf"] = False
    inspection = core.inspect_inputs(config)
    assert inspection["ok"], inspection
    assert inspection["photo_count"] == 3
    result = core.run_job(config, "cards")
    assert result["success"] == 3
    assert {_decode(path) for path in _pngs(Path(result["output_dir"]))} == {"00001", "00002", "00003"}


def test_zip_path_traversal_cannot_write_outside_workspace(tmp_path):
    config = _config(tmp_path)
    archive_path = tmp_path / "invalid.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../../unexpected-card-test.txt", b"do not write")
        archive.writestr("/absolute/00001.jpg", b"invalid")
    config["photo_path"] = str(archive_path)
    inspection = core.inspect_inputs(config)
    assert not inspection["ok"]
    assert not (tmp_path.parent / "unexpected-card-test.txt").exists()


def test_excel_numeric_id_with_zero_number_format(tmp_path):
    config = _config(tmp_path)
    workbook = load_workbook(config["excel_path"])
    workbook.active["A2"] = 1
    workbook.active["A2"].number_format = "00000"
    workbook.save(config["excel_path"])
    inspection = core.inspect_inputs(config)
    assert inspection["ok"], inspection
    assert inspection["students"][0]["student_id"] == "00001"


def test_custom_column_names(tmp_path):
    config = _config(tmp_path)
    workbook = load_workbook(config["excel_path"])
    workbook.active["A1"], workbook.active["B1"], workbook.active["C1"] = "ID", "English", "Chinese"
    workbook.save(config["excel_path"])
    config.update(column_id="ID", column_eng="English", column_chi="Chinese")
    inspection = core.inspect_inputs(config)
    assert inspection["ok"], inspection
    assert inspection["students"][0]["english_name"] == "ALEX CHAN"


def test_missing_required_column_is_actionable(tmp_path):
    config = _config(tmp_path)
    config["column_id"] = "does_not_exist"
    inspection = core.inspect_inputs(config)
    assert not inspection["ok"]
    assert "does_not_exist" in _messages(inspection)


def test_cards_can_be_generated_without_pdf_back(tmp_path):
    config = _config(tmp_path)
    config.update(make_pdf=False, back_path="")
    assert core.inspect_inputs(config)["ok"]
    result = core.run_job(config, "cards")
    assert result["success"] == 3
    assert not _pdfs(Path(result["output_dir"]))


def test_mismatched_mask_is_blocked(tmp_path):
    config = _config(tmp_path)
    Image.new("L", (60, 60), 255).save(config["mask_path"])
    inspection = core.inspect_inputs(config)
    assert not inspection["ok"], "A mismatched mask must be caught before rendering"


def test_cancel_before_processing_does_not_claim_success(tmp_path):
    config = _config(tmp_path)
    result = core.run_job(config, "cards", cancelled=lambda: True)
    assert result["cancelled"]
    assert result["success"] == 0
    assert not _pngs(Path(result["output_dir"]))


def test_unknown_mode_is_rejected(tmp_path):
    config = _config(tmp_path)
    with pytest.raises((ValueError, KeyError)):
        core.run_job(config, "unrecognized_mode")


@pytest.mark.parametrize("mode", ["cards", "crop", "pdf"])
@pytest.mark.parametrize("nested", [False, True])
def test_output_cannot_be_inside_scanned_input(mode, nested, tmp_path):
    config = _config(tmp_path)
    source = Path(config["photo_path"])
    if mode == "pdf":
        source = tmp_path / "existing_fronts"
        source.mkdir()
        Image.new("RGB", (648, 1050), "white").save(source / "00001_ID.png")
        config["pdf_input_dir"] = str(source)
    config["output_dir"] = str(source / "nested_output" if nested else source)
    inspection = core.inspect_inputs(config, mode)
    assert not inspection["ok"], "Scanning prior outputs can silently duplicate photos or PDFs"
    assert inspection["errors"]
