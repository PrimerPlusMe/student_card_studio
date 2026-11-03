"""Stage-two offline model validation against a public-domain NASA portrait."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import time

import pytest
from PIL import Image

from student_card.core import create_demo, inspect_inputs, run_job
from student_card.face import FaceDetector


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "assets" / "face_detection_yunet_2023mar.onnx"
PORTRAIT = ROOT / "tests" / "fixtures" / "astronaut.png"


@pytest.fixture
def astronaut():
    with Image.open(PORTRAIT) as source:
        return source.convert("RGB")


def _assert_valid_face(face, image):
    assert face is not None
    x, y, width, height = face["box"]
    nose_x, nose_y = face["nose"]
    assert width > 0 and height > 0
    assert 0 <= x < x + width <= image.width + 1
    assert 0 <= y < y + height <= image.height + 1
    assert x < nose_x < x + width
    assert y < nose_y < y + height


def test_yunet_single_real_face_and_nose_landmark(astronaut, record_property):
    detector = FaceDetector()
    started = time.perf_counter()
    face = detector.detect(astronaut)
    record_property("detect_seconds", round(time.perf_counter() - started, 4))
    _assert_valid_face(face, astronaut)
    assert face["count"] == 1
    x, y, width, height = face["box"]
    assert x < 230 < x + width and y < 130 < y + height, "Detection should surround the visible astronaut face"
    assert detector.metadata["backend"] == "yunet"
    assert len(detector.metadata["sha256"]) == 64


def test_yunet_two_people_selects_largest_face(astronaut):
    # The left portrait has twice the linear size of the right portrait.
    image = Image.new("RGB", (800, 540), "white")
    image.paste(astronaut, (0, 0))
    image.paste(astronaut.resize((256, 256)), (530, 120))
    face = FaceDetector().detect(image)
    _assert_valid_face(face, image)
    assert face["count"] == 2
    assert face["box"][0] < 400, "The larger face on the left must be selected"


def test_yunet_empty_image_has_no_false_face():
    assert FaceDetector().detect(Image.new("RGB", (640, 480), "white")) is None


def test_yunet_model_loads_from_unicode_path(tmp_path, astronaut):
    folder = tmp_path / "中文模型目录"
    folder.mkdir()
    destination = folder / "人脸定位.onnx"
    shutil.copyfile(MODEL, destination)
    detector = FaceDetector(str(destination), "yunet")
    _assert_valid_face(detector.detect(astronaut), astronaut)


def test_yunet_missing_and_corrupt_models_fail_explicitly(tmp_path):
    with pytest.raises(RuntimeError, match="YuNet"):
        FaceDetector(str(tmp_path / "missing.onnx"), "yunet")
    model = tmp_path / "broken.onnx"
    model.write_bytes(b"this is not an ONNX model")
    with pytest.raises(RuntimeError):
        FaceDetector(str(model), "yunet")


@pytest.mark.parametrize("mode", ["cards", "crop"])
def test_missing_model_is_caught_before_a_job_starts(tmp_path, mode):
    config = create_demo(tmp_path / "demo")
    config.update(output_dir=str(tmp_path / "jobs"), model_path=str(tmp_path / "missing.onnx"))
    inspection = inspect_inputs(config, mode)
    assert not inspection["ok"]
    assert any("YuNet" in error for error in inspection["errors"])
    assert not Path(config["output_dir"]).exists()


def test_pdf_only_does_not_require_a_face_model(tmp_path):
    config = create_demo(tmp_path / "demo")
    fronts = tmp_path / "fronts"
    fronts.mkdir()
    Image.new("RGB", (648, 1050), "white").save(fronts / "00001_ID.png")
    config.update(output_dir=str(tmp_path / "jobs"), pdf_input_dir=str(fronts), model_path=str(tmp_path / "missing.onnx"))
    inspection = inspect_inputs(config, "pdf")
    assert inspection["ok"], inspection


def test_haar_remains_an_explicit_compatible_backend(astronaut):
    detector = FaceDetector(backend="haar")
    _assert_valid_face(detector.detect(astronaut), astronaut)
    assert detector.metadata["backend"] == "haar"


def test_multi_person_and_no_face_marked_for_manual_review(tmp_path, astronaut):
    config = create_demo(tmp_path / "demo")
    config.update(output_dir=str(tmp_path / "jobs"), make_pdf=False)
    folder = Path(config["photo_path"])
    astronaut.save(folder / "00001.jpg")
    Image.new("RGB", (600, 850), "white").save(folder / "00002.jpg")
    people = Image.new("RGB", (800, 540), "white")
    people.paste(astronaut, (0, 0))
    people.paste(astronaut.resize((256, 256)), (530, 120))
    people.save(folder / "00003.jpg")
    result = run_job(config)
    assert result["success"] == 3
    assert result["review"] == 2
    manifest = json.loads((Path(result["output_dir"]) / "manifest.json").read_text(encoding="utf-8"))
    records = {row["student_id"]: row for row in manifest["records"]}
    assert records["00001"]["status"] == "success"
    assert records["00002"]["status"] == records["00003"]["status"] == "review"
    assert "未检测到人脸" in records["00002"]["message"]
    assert "2" in records["00003"]["message"]
    assert manifest["summary"]["detector"]["backend"] == "yunet"
