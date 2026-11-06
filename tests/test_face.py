"""Offline model checks plus deterministic crop-boundary regressions."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import pytest

from student_card import face

PORTRAIT = Path(__file__).parent / "fixtures" / "astronaut.png"


def test_yunet_real_face_and_blank():
    with Image.open(PORTRAIT) as image:
        arr = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        x, y, w, h = face.detect_face(arr)
        assert x < 230 < x + w and y < 130 < y + h
    assert face.detect_face(np.full((320, 320, 3), 255, dtype=np.uint8)) is None


def test_largest_face_selected():
    with Image.open(PORTRAIT) as portrait:
        image = Image.new("RGB", (800, 540), "white")
        image.paste(portrait, (0, 0))
        image.paste(portrait.resize((256, 256)), (530, 120))
    box = face.detect_face(cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR))
    assert box is not None and box[0] < 400


@pytest.mark.parametrize("box", [None, (0, 0, 100, 100), (290, 385, 90, 110), (0, 0, 900, 1000)])
def test_crop_keeps_ratio_near_boundaries(monkeypatch, box):
    monkeypatch.setattr(face, "detect_face", lambda image: box)
    cropped = face.crop_for_eclass(Image.new("RGB", (301, 403), "red"))
    assert cropped.width * 13 == cropped.height * 10
    assert 0 < cropped.width <= 301 and 0 < cropped.height <= 403


def test_unicode_path_and_exif_orientation(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(face, "detect_face", lambda image: seen.append(image.shape) or None)
    path = tmp_path / "學生照片.jpg"
    image = Image.new("RGB", (400, 300), "white")
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, exif=exif)
    cropped = face.crop_for_eclass(path)
    assert seen[0][:2] == (400, 300)
    assert cropped.size == (300, 390)


def test_small_image():
    assert face.crop_for_eclass(Image.new("RGB", (1, 1))).size == (10, 13)
    assert face.crop_for_eclass(Image.new("RGB", (3, 4))).size == (10, 13)


def test_large_inference_maps_coordinates_back(monkeypatch):
    class Detector:
        def setInputSize(self, size):
            assert size == (1200, 600)

        def detect(self, image):
            assert image.shape[:2] == (600, 1200)
            return None, np.array([[100, 50, 200, 150]], dtype=float)

    monkeypatch.setattr(face, "get_detector", lambda: Detector())
    assert face.detect_face(np.zeros((1200, 2400, 3), dtype=np.uint8)) == (200, 100, 400, 300)


def test_green_background_and_tiny_matting():
    assert face.remove_green_screen_to_white(Image.new("RGB", (80, 100), (0, 255, 0))).getpixel((40, 50)) == (255, 255, 255)
    assert face.remove_green_screen_to_white(Image.new("RGB", (1, 1), "white")).size == (1, 1)


def test_missing_and_corrupt_model(monkeypatch, tmp_path):
    monkeypatch.setattr(face, "_detector", None)
    monkeypatch.setattr(face, "MODEL_PATH", tmp_path / "missing.onnx")
    with pytest.raises(FileNotFoundError, match="YuNet"):
        face.get_detector()
    face.MODEL_PATH.write_bytes(b"not an ONNX model")
    with pytest.raises(cv2.error):
        face.get_detector()


def test_parallel_detector_calls():
    with Image.open(PORTRAIT) as image:
        arr = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    with ThreadPoolExecutor(max_workers=2) as pool:
        boxes = list(pool.map(face.detect_face, [arr, arr]))
    assert boxes[0] == boxes[1]