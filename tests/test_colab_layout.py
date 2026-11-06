"""Independent pixel/geometry oracle for the original Colab school layout.

No school template, proprietary font, or student record is bundled in these tests.
"""
from io import BytesIO
from pathlib import Path

from barcode import Code128
from barcode.writer import ImageWriter
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance
import pytest
import zxingcpp

from student_card import core, face
from student_card.demo import create_demo


@pytest.fixture
def config(tmp_path):
    return create_demo(tmp_path / "school")


def test_separate_chinese_english_names(config):
    rows = core.read_students(config["excel_path"])
    assert rows[0]["english_name"] == "ALEX CHAN"
    assert rows[0]["chinese_name"] == "陳同學"
    assert rows[1]["chinese_name"] == "/"


@pytest.mark.parametrize("chinese", ["陳同學", "", "/", "／", "nan"])
def test_original_mask_text_barcode_coordinates_pixel_oracle(config, tmp_path, monkeypatch, chinese):
    tile = Image.new("RGB", (340, 340), "#268ac2")
    monkeypatch.setattr(core, "process_card_face", lambda *args, **kwargs: tile.copy())
    sid, english = "h000001", "Alex Chan"
    output = tmp_path / "student.png"
    actual = core.generate_single_card(config["front_template"],
        str(Path(config["photos_dir"]) / "00001.jpg"), str(output), english, sid, "1M", "1",
        chinese_name=chinese, mask_path=config["mask_path"])
    # Direct translation of Notebook generate_id_card(), independent of our renderer.
    with Image.open(config["front_template"]) as source:
        expected = source.convert("RGB")
    with Image.open(config["mask_path"]) as source:
        mask = source.convert("L")
    canvas = Image.new("RGB", expected.size, "white")
    canvas.paste(tile, (155, 347))
    expected = Image.composite(canvas, expected, mask)
    draw = ImageDraw.Draw(expected)
    if chinese not in {"", "/", "／", "nan"}:
        draw.text((324, 742), english, font=core.get_font(None, 46), fill="black", anchor="mm")
        draw.text((324, 812), chinese, font=core.get_font(None, 65), fill="black", anchor="mm")
    else:
        draw.text((324, 768), english, font=core.get_font(None, 46), fill="black", anchor="mm")
    stream = BytesIO()
    Code128(sid, writer=ImageWriter()).write(stream, options={"write_text": False,
        "module_height": 10.0, "quiet_zone": 1.0, "background": "white"})
    stream.seek(0)
    with Image.open(stream) as image:
        barcode = image.convert("RGB").resize((350, 90), Image.Resampling.NEAREST)
    expected.paste(barcode, (149, 863))
    draw.text((324, 960), sid, font=core.get_font(None, 42), fill="black", anchor="mt")
    assert np.array_equal(np.asarray(actual), np.asarray(expected))
    assert actual.getpixel((50, 500)) == expected.getpixel((50, 500))
    assert actual.getpixel((324, 516)) == tile.getpixel((0, 0))
    with Image.open(output) as saved:
        assert saved.format == "PNG" and saved.size == (649, 1033)
        assert zxingcpp.read_barcode(saved).text == sid
    actual.close()


@pytest.mark.parametrize("sid", ["00001", "h000001", "AbC0123456789"])
def test_barcode_reads_original_case_and_zeros(sid):
    with core._barcode_image(sid) as barcode:
        result = zxingcpp.read_barcode(barcode)
        assert result is not None and result.text == sid
        assert barcode.size == (350, 90)


def test_card_face_matches_notebook_resize_crop_formula(monkeypatch):
    image = Image.new("RGB", (1000, 1000), "#6699aa")
    draw = ImageDraw.Draw(image)
    draw.rectangle((400, 200, 600, 700), fill="#aa4422")
    monkeypatch.setattr(face, "detect_face_landmarks", lambda arr: {
        "box": (400, 200, 200, 300), "nose": (500, 400), "count": 1})
    actual = face.process_card_face(image)
    bright = ImageEnhance.Brightness(image.convert("RGBA")).enhance(1.2)
    scale = (170 * 2) * 0.32 / 200
    resized = bright.resize((int(1000 * scale), int(1000 * scale)), Image.Resampling.LANCZOS)
    left, top = int(500 * scale) - 170, int(400 * scale) - 170 - 10
    expected = resized.crop((left, top, left + 340, top + 340)).convert("RGB")
    assert actual.size == (340, 340)
    assert np.array_equal(np.asarray(actual), np.asarray(expected))


def test_outside_photo_padding_is_white_not_old_template(monkeypatch):
    monkeypatch.setattr(face, "detect_face_landmarks", lambda arr: {
        "box": (0, 0, 100, 100), "nose": (1, 1), "count": 1})
    with face.process_card_face(Image.new("RGB", (100, 100), "red")) as tile:
        assert tile.getpixel((0, 0)) == (255, 255, 255)
        assert tile.size == (340, 340)


def test_nose_landmarks_are_scaled_to_source(monkeypatch):
    class Detector:
        def setInputSize(self, size):
            assert size == (1200, 600)

        def detect(self, image):
            row = [100, 50, 200, 150, 130, 80, 240, 80, 190, 130, 140, 170, 230, 170, 0.99]
            return None, np.array([row])
    monkeypatch.setattr(face, "get_detector", lambda: Detector())
    result = face.detect_face_landmarks(np.zeros((1200, 2400, 3), dtype=np.uint8))
    assert result["box"] == (200, 100, 400, 300)
    assert result["nose"] == (380, 260) and result["count"] == 1


def test_real_face_nose_is_inside_face_box():
    import cv2
    with Image.open(Path(__file__).parent / "fixtures" / "astronaut.png") as image:
        result = face.detect_face_landmarks(cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR))
    x, y, w, h = result["box"]
    nx, ny = result["nose"]
    assert x <= nx <= x + w and y <= ny <= y + h


def test_noface_formula_returns_complete_white_padded_tile(monkeypatch):
    monkeypatch.setattr(face, "detect_face_landmarks", lambda arr: None)
    with face.process_card_face(Image.new("RGB", (600, 800), "white")) as tile:
        assert tile.size == (340, 340)
        assert tile.getextrema() == ((255, 255), (255, 255), (255, 255))


def test_non_school_template_rejected(config):
    Image.new("RGB", (1012, 638), "white").save(config["front_template"])
    with pytest.raises(ValueError, match="649×1033"):
        core.batch_generate_cards(**config)
    assert not Path(config["output_dir"]).exists()


@pytest.mark.parametrize("brightness", [0, float("nan"), 9])
def test_invalid_brightness_fails_before_job(config, brightness):
    with pytest.raises(ValueError, match="Brightness"):
        core.batch_generate_cards(**config, brightness=brightness)
    assert not Path(config["output_dir"]).exists()


def test_eclass_maximal_crop_not_closeup(monkeypatch):
    monkeypatch.setattr(face, "detect_face", lambda arr: (2900, 500, 200, 300))
    image = Image.new("RGB", (6000, 4000), "white")
    with face.crop_for_eclass(image) as crop:
        assert crop.size == (3070, 3991)
        assert crop.width * crop.height / (6000 * 4000) > 0.5


@pytest.mark.parametrize("problem", ["missing", "dimensions", "white", "outside"])
def test_mask_is_validated_before_any_job(config, problem):
    path = Path(config["mask_path"])
    if problem == "missing":
        path.unlink()
    elif problem == "dimensions":
        Image.new("L", (50, 50), 0).save(path)
    elif problem == "white":
        Image.new("L", (649, 1033), 255).save(path)
    else:
        mask = Image.new("L", (649, 1033), 0)
        ImageDraw.Draw(mask).rectangle((1, 1, 200, 200), fill=255)
        mask.save(path)
    with pytest.raises((ValueError, FileNotFoundError)):
        core.batch_generate_cards(**config)
    assert not Path(config["output_dir"]).exists()


def test_auto_find_original_assets_and_explicit_bad_font(config):
    config.pop("mask_path")
    config["export_3x4_pdf"] = False
    assert core.batch_generate_cards(**config).success == 3
    with pytest.raises(FileNotFoundError):
        core.batch_generate_cards(**config, font_eng_path="missing-font.ttf")


def test_long_name_shrinks_without_changing_center(monkeypatch):
    calls = []
    class Draw:
        def textlength(self, text, font):
            return len(text) * font.size

        def text(self, xy, text, **kwargs):
            calls.append((xy, kwargs))
    core._draw_fitted(Draw(), (324, 742), "A" * 60, None, 46, 609)
    assert calls[0][0] == (324, 742)
    assert calls[0][1]["anchor"] == "mm" and calls[0][1]["font"].size <= 10