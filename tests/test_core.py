"""Regression coverage for the current card/crop/3×4 review workflows."""
import hashlib
from pathlib import Path
import re

from openpyxl import load_workbook
from PIL import Image
from pypdf import PdfReader
import pytest

from student_card import core
from student_card.demo import create_demo


@pytest.fixture
def config(tmp_path):
    return create_demo(tmp_path / "demo")


def edit_book(config, change):
    book = load_workbook(config["excel_path"])
    try:
        change(book.active)
        book.save(config["excel_path"])
    finally:
        book.close()


def run(config, **options):
    return core.batch_generate_cards(**dict(config, **options))


def test_leading_zeros_and_names(config):
    rows = core.read_students(config["excel_path"])
    assert [row["student_id"] for row in rows] == ["00001", "00002", "00003"]
    assert rows[0]["class_number"] == "1"
    assert not rows[0]["issues"]


def test_numeric_zero_format(config):
    def change(sheet):
        sheet["A2"] = 1
        sheet["A2"].number_format = "00000"
    edit_book(config, change)
    assert core.read_students(config["excel_path"])[0]["student_id"] == "00001"


@pytest.mark.parametrize("value,expected", [(None, ""), (float("nan"), ""), (2.0, "2"),
                                             ("00001", "00001"), ("A.0", "A.0"), (0, "0")])
def test_clean_str(value, expected):
    assert core.clean_str(value) == expected


def test_alias_fallback_and_zero_class_number(config):
    def change(sheet):
        sheet["B2"] = None
        sheet["C2"] = "陳同學"
        sheet["E2"] = 0
    edit_book(config, change)
    row = core.read_students(config["excel_path"])[0]
    assert row["name"] == "陳同學"
    assert row["class_number"] == "0"


def test_header_aliases_and_whitespace(config):
    def change(sheet):
        sheet["A1"], sheet["B1"], sheet["D1"] = " id ", " name ", "班別"
    edit_book(config, change)
    assert core.read_students(config["excel_path"])[0]["student_id"] == "00001"


def test_missing_column_fails_before_output(config):
    edit_book(config, lambda sheet: setattr(sheet["A1"], "value", "unknown"))
    with pytest.raises(ValueError, match="Missing required column"):
        run(config)
    assert not Path(config["output_dir"]).exists()


def test_blank_rows_ignored_and_empty_workbook_rejected(config):
    edit_book(config, lambda sheet: sheet.append([None, None, None, None, None]))
    assert len(core.read_students(config["excel_path"])) == 3
    edit_book(config, lambda sheet: sheet.delete_rows(2, sheet.max_row))
    with pytest.raises(ValueError, match="empty"):
        run(config)


def test_formula_row_reported_without_stopping_other_students(config):
    edit_book(config, lambda sheet: setattr(sheet["A2"], "value", '=TEXT(1,"00000")'))
    result = run(config, export_3x4_pdf=False)
    assert (result.success, result.failed) == (2, 1)
    assert "formula" in result.errors[0]


def test_cards_pdf_progress_and_unchanged_inputs(config):
    root = Path(config["photos_dir"]).parent
    before = {p: hashlib.sha256(p.read_bytes()).digest() for p in root.rglob("*") if p.is_file()}
    progress = []
    result = run(config, progress_callback=lambda *args: progress.append(args))
    assert (result.total, result.success, result.failed, result.errors) == (3, 3, 0, [])
    output = Path(result.output_dir)
    assert len(list((output / "single_cards").glob("*.png"))) == 3
    assert len(list((output / "cropped_photos").glob("*.jpg"))) == 3
    assert len(list(output.glob("*.pdf"))) == 1
    reader = PdfReader(result.review_pdf)
    assert len(reader.pages) == 1
    assert float(reader.pages[0].mediabox.width) * 25.4 / 72 == pytest.approx(210, abs=0.1)
    assert float(reader.pages[0].mediabox.height) * 25.4 / 72 == pytest.approx(297, abs=0.1)
    assert progress[-1][:2] == (3, 3)
    for p, digest in before.items():
        assert hashlib.sha256(p.read_bytes()).digest() == digest


def test_no_pdf_when_disabled(config):
    result = run(config, export_3x4_pdf=False)
    assert result.success == 3 and not result.review_pdf
    assert not list(Path(result.output_dir).rglob("*.pdf"))


def test_repeated_job_has_unique_output(config):
    first = run(config, export_3x4_pdf=False)
    second = run(config, export_3x4_pdf=False)
    assert first.output_dir != second.output_dir
    assert len(list(Path(first.output_dir).rglob("*.jpg"))) == 3
    assert len(list(Path(first.output_dir).rglob("*.png"))) == 3


@pytest.mark.parametrize("problem", ["missing", "corrupt", "multiple"])
def test_bad_photos_are_failed_not_blank_success(config, problem):
    photo = Path(config["photos_dir"]) / "00001.jpg"
    if problem == "missing":
        photo.unlink()
    elif problem == "corrupt":
        photo.write_bytes(b"not an image")
    else:
        with Image.open(photo) as img:
            img.save(photo.with_suffix(".PNG"))
    result = run(config, export_3x4_pdf=False)
    assert (result.success, result.failed) == (2, 1)
    assert len(list(Path(result.output_dir).rglob("*.jpg"))) == 2
    assert len(list(Path(result.output_dir).rglob("*.png"))) == 2


def test_duplicate_ids_do_not_overwrite(config):
    edit_book(config, lambda sheet: setattr(sheet["A3"], "value", "00001"))
    result = run(config, export_3x4_pdf=False)
    assert (result.success, result.failed) == (1, 2)
    assert all("Duplicate" in error for error in result.errors)


def test_uppercase_photo_extension(config):
    photo = Path(config["photos_dir"]) / "00001.jpg"
    photo.rename(photo.with_suffix(".JPG"))
    assert run(config, export_3x4_pdf=False).success == 3


def test_unsafe_names_cannot_escape_output(config):
    def change(sheet):
        sheet["B2"], sheet["D2"] = '../../a:b\\name?*', "../CON"
    edit_book(config, change)
    result = run(config, export_3x4_pdf=False)
    assert result.success == 3
    cards = list((Path(result.output_dir) / "single_cards").iterdir())
    assert len(cards) == 3
    assert not any(re.search(r'[<>:"/\\|?*]', p.name) for p in cards)


def test_long_unicode_names_fit_filesystem_limits(config):
    def change(sheet):
        sheet["B2"], sheet["D2"] = "陳同學" * 100, "班級" * 100
    edit_book(config, change)
    result = run(config, export_3x4_pdf=False)
    assert result.success == 3
    assert all(len(p.name.encode("utf-8")) <= 255 for p in Path(result.output_dir).rglob("*.*"))


@pytest.mark.parametrize("mode", ["cards", "crop"])
@pytest.mark.parametrize("nested", [False, True])
def test_output_must_not_be_in_source(config, mode, nested):
    source = Path(config["photos_dir"])
    destination = source / "outputs" if nested else source
    with pytest.raises(ValueError, match="outside"):
        if mode == "cards":
            run(config, output_dir=str(destination))
        else:
            core.batch_crop_eclass_only(str(source), str(destination))


def test_crop_batch_and_corrupt_photo(config):
    (Path(config["photos_dir"]) / "broken.JPG").write_bytes(b"broken")
    result = core.batch_crop_eclass_only(config["photos_dir"], config["output_dir"])
    assert (result.total, result.success, result.failed) == (4, 3, 1)
    assert not (Path(result.output_dir) / "broken.JPG").exists()
    for path in Path(result.output_dir).iterdir():
        with Image.open(path) as image:
            assert image.width * 13 == image.height * 10


def test_pdf_twelve_per_page_and_cell_order(tmp_path):
    colors = [(230, 20, 20), (20, 210, 20), (20, 20, 230)]
    cards = [Image.new("RGB", (120, 80), colors[i % 3]) for i in range(13)]
    try:
        path = tmp_path / "review.pdf"
        core.create_3x4_review_pdf(iter(cards), str(path))
        pages = PdfReader(path).pages
        assert len(pages) == 2
        for page_number, page in enumerate(pages):
            image = page.images[0].image.convert("RGB")
            for index in range(12 if page_number == 0 else 1):
                pixel = image.getpixel((int((index % 3 + 0.5) * image.width / 3),
                                        int((index // 3 + 0.5) * image.height / 4)))
                expected = colors[(page_number * 12 + index) % 3]
                assert max(abs(a - b) for a, b in zip(pixel, expected)) < 15
    finally:
        for card in cards:
            card.close()


def test_pdf_failure_preserves_existing_file(tmp_path):
    output = tmp_path / "review.pdf"
    output.write_bytes(b"previous PDF")
    with pytest.raises(FileNotFoundError):
        core.create_3x4_review_pdf([tmp_path / "missing.jpg"], str(output))
    assert output.read_bytes() == b"previous PDF"
    with pytest.raises(ValueError, match="No cards"):
        core.create_3x4_review_pdf([], str(output))
    assert not list(tmp_path.glob(".review-*"))


def test_pdf_export_error_is_reported(config, monkeypatch):
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(core, "create_3x4_review_pdf", fail)
    result = run(config)
    assert result.success == 3 and not result.review_pdf
    assert "disk full" in result.errors[0]


def test_removed_double_sided_api():
    assert not hasattr(core, "create_double_sided_pdf")


def test_stats_errors_are_not_shared():
    first, second = core.ProcessStats(), core.ProcessStats()
    first.errors.append("one")
    assert second.errors == []