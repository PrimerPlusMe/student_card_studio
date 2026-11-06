"""Lossless front/back export, sorted merge, partial failures, and source safety."""
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw
from pypdf import PdfReader
import pytest

from student_card import core
from student_card.demo import create_demo
from student_card.pdf import create_student_pdf, merge_student_pdfs


@pytest.fixture
def images(tmp_path):
    fronts = tmp_path / "fronts"
    fronts.mkdir()
    for name, color in (("002.png", "red"), ("001.png", "blue"), ("003.JPG", "green")):
        with Image.new("RGB", (80, 120), color) as image:
            ImageDraw.Draw(image).rectangle((10, 10, 20, 20), fill="white")
            image.save(fronts / name)
    back = tmp_path / "back.png"
    Image.new("RGB", (100, 140), "yellow").save(back)
    return fronts, back, tmp_path / "output"


def pixels(page):
    return page.images[0].image.convert("RGB").tobytes()


def test_individual_and_combined_lossless_order_and_size(images):
    fronts, back, output = images
    before = {p: hashlib.sha256(p.read_bytes()).digest() for p in [back, *fronts.iterdir()]}
    progress = []
    result = core.batch_generate_pdfs(str(fronts), str(back), str(output),
                                      progress_callback=lambda *args: progress.append(args))
    assert (result.total, result.success, result.failed, result.pdf_success, result.pdf_failed) == (3, 3, 0, 3, 0)
    assert not result.errors
    combined = PdfReader(result.combined_pdf)
    assert len(combined.pages) == 6
    for index, front in enumerate(sorted(fronts.iterdir(), key=lambda path: path.name.casefold())):
        individual = PdfReader(Path(result.individual_pdf_dir) / f"{front.stem}.pdf")
        assert len(individual.pages) == 2
        for offset, source in enumerate((front, back)):
            with Image.open(source) as image:
                expected = image.convert("RGB").tobytes()
            for page in (individual.pages[offset], combined.pages[index * 2 + offset]):
                assert pixels(page) == expected
                assert float(page.mediabox.width) * 25.4 / 72 == pytest.approx(54, abs=0.001)
                assert float(page.mediabox.height) * 25.4 / 72 == pytest.approx(85.6, abs=0.001)
    assert progress[-1][:2] == (3, 3)
    assert all(hashlib.sha256(p.read_bytes()).digest() == digest for p, digest in before.items())


def test_transparency_white_and_aspect_preserved(tmp_path):
    front = Image.new("RGBA", (100, 100), (255, 0, 0, 0))
    front.putpixel((50, 50), (255, 0, 0, 255))
    path = tmp_path / "one.pdf"
    create_student_pdf(front, front, path, 54, 85.6)
    page = PdfReader(path).pages[0]
    image = page.images[0].image.convert("RGB")
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert image.getpixel((50, 50)) == (255, 0, 0)
    content = page.get_contents().get_data().decode("ascii")
    transform = content.split("\n")[1].split()
    assert float(transform[1]) == pytest.approx(float(transform[4]))  # square image stays square


def test_pdf_only_does_not_need_detector(images, monkeypatch):
    def fail():
        raise AssertionError("PDF export must not load the detector")
    monkeypatch.setattr(core, "get_detector", fail)
    fronts, back, output = images
    assert core.batch_generate_pdfs(str(fronts), str(back), str(output)).success == 3


@pytest.mark.parametrize("nested", [False, True])
def test_pdf_output_cannot_be_inside_source(images, nested):
    fronts, back, _ = images
    output = fronts / "out" if nested else fronts
    with pytest.raises(ValueError, match="outside"):
        core.batch_generate_pdfs(str(fronts), str(back), str(output))


@pytest.mark.parametrize("kind", ["missing", "corrupt"])
def test_bad_back_fails_before_creating_job(images, kind):
    fronts, back, output = images
    if kind == "missing":
        back.unlink()
    else:
        back.write_bytes(b"broken")
    with pytest.raises((FileNotFoundError, OSError)):
        core.batch_generate_pdfs(str(fronts), str(back), str(output))
    assert not output.exists()


def test_corrupt_front_reported_and_only_successes_combined(images):
    fronts, back, output = images
    (fronts / "broken.png").write_bytes(b"broken")
    result = core.batch_generate_pdfs(str(fronts), str(back), str(output))
    assert (result.total, result.success, result.failed) == (4, 3, 1)
    assert len(PdfReader(result.combined_pdf).pages) == 6
    assert not (Path(result.individual_pdf_dir) / "broken.pdf").exists()


def test_duplicate_stems_cannot_silently_overwrite(images):
    fronts, back, output = images
    Image.new("RGB", (40, 50), "white").save(fronts / "001.JPG")
    result = core.batch_generate_pdfs(str(fronts), str(back), str(output))
    assert (result.success, result.failed) == (2, 2)
    assert len(PdfReader(result.combined_pdf).pages) == 4


def test_back_inside_source_is_not_exported_as_student(images):
    fronts, back, output = images
    inside = fronts / "back.png"
    inside.write_bytes(back.read_bytes())
    result = core.batch_generate_pdfs(str(fronts), str(inside), str(output))
    assert result.success == 3


def test_combination_failure_keeps_individual_pdfs(images, monkeypatch):
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(core, "merge_student_pdfs", fail)
    fronts, back, output = images
    result = core.batch_generate_pdfs(str(fronts), str(back), str(output))
    assert result.success == 3 and result.combined_pdf == ""
    assert len(list(Path(result.individual_pdf_dir).glob("*.pdf"))) == 3
    assert "disk full" in result.errors[-1]


def test_all_fronts_failed_do_not_claim_pdf_output(images):
    fronts, back, output = images
    for file in fronts.iterdir():
        file.write_bytes(b"broken")
    result = core.batch_generate_pdfs(str(fronts), str(back), str(output))
    assert result.success == 0 and result.failed == 3
    assert not result.combined_pdf and not result.individual_pdf_dir


def test_repeated_pdf_jobs_are_unique(images):
    fronts, back, output = images
    first = core.batch_generate_pdfs(str(fronts), str(back), str(output))
    second = core.batch_generate_pdfs(str(fronts), str(back), str(output))
    assert first.output_dir != second.output_dir
    assert Path(first.combined_pdf).is_file()


def test_card_job_with_auto_discovered_back_and_review(tmp_path):
    config = create_demo(tmp_path / "demo")
    result = core.batch_generate_cards(**config, export_student_pdfs=True)
    assert result.success == result.pdf_success == 3
    assert result.failed == result.pdf_failed == 0 and not result.errors
    assert Path(result.review_pdf).is_file()
    assert len(PdfReader(result.combined_pdf).pages) == 6


def test_card_job_disabled_pdf_ignores_back(tmp_path):
    config = create_demo(tmp_path / "demo")
    result = core.batch_generate_cards(**config, back_path="missing.png", export_student_pdfs=False)
    assert result.success == 3 and not result.combined_pdf


def test_card_job_keeps_card_results_if_export_setup_fails(tmp_path, monkeypatch):
    config = create_demo(tmp_path / "demo")
    def fail(*args):
        raise OSError("back volume disconnected")
    monkeypatch.setattr(core, "_export_student_pdfs", fail)
    result = core.batch_generate_cards(**config, export_student_pdfs=True)
    assert result.success == 3 and result.failed == 0
    assert result.pdf_failed == 3 and not result.combined_pdf
    assert Path(result.review_pdf).is_file()
    assert "disconnected" in result.errors[-1]


def test_merge_rejects_non_two_page_pdf_without_overwrite(tmp_path):
    from pypdf import PdfWriter
    invalid = tmp_path / "one-page.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with invalid.open("wb") as stream:
        writer.write(stream)
    writer.close()
    output = tmp_path / "combined.pdf"
    output.write_bytes(b"previous")
    with pytest.raises(ValueError, match="two pages"):
        merge_student_pdfs([invalid], output)
    assert output.read_bytes() == b"previous"


def test_invalid_back_blocks_card_job_before_output(tmp_path):
    config = create_demo(tmp_path / "demo")
    with pytest.raises(FileNotFoundError):
        core.batch_generate_cards(**config, export_student_pdfs=True, back_path="missing.png")
    assert not Path(config["output_dir"]).exists()


@pytest.mark.parametrize("width,height", [(0, 85), (54, float("nan")), (501, 85)])
def test_invalid_pdf_size(images, width, height):
    fronts, back, output = images
    with pytest.raises(ValueError, match="dimensions"):
        core.batch_generate_pdfs(str(fronts), str(back), str(output), width, height)
    assert not output.exists()


def test_atomic_failure_preserves_old_file(images, tmp_path):
    fronts, back, _ = images
    target = tmp_path / "old.pdf"
    target.write_bytes(b"previous")
    with pytest.raises(FileNotFoundError):
        create_student_pdf(fronts / "missing.png", back, target)
    assert target.read_bytes() == b"previous"
    with pytest.raises(ValueError, match="No PDFs"):
        merge_student_pdfs([], target)
    assert target.read_bytes() == b"previous"