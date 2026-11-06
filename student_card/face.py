"""
Face detection, eClass alignment/cropping, and background matting utilities.
"""
from pathlib import Path
from threading import RLock
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
MODEL_PATH = PROJECT_ROOT / "assets" / "face_detection_yunet_2023mar.onnx"

_detector = None
_detector_lock = RLock()

def get_detector():
    """Lazy load cv2.FaceDetectorYN model."""
    global _detector
    with _detector_lock:
        if _detector is None:
            if not MODEL_PATH.is_file():
                raise FileNotFoundError(f"YuNet model not found at {MODEL_PATH}")
            _detector = cv2.FaceDetectorYN.create(
                model=str(MODEL_PATH), config="", input_size=(320, 320),
                score_threshold=0.6, nms_threshold=0.3, top_k=5000,
                backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
                target_id=cv2.dnn.DNN_TARGET_CPU,
            )
        return _detector

def detect_face_landmarks(image_bgr: np.ndarray) -> Optional[dict]:
    """Return the largest face and its nose in original-image coordinates."""
    h, w = image_bgr.shape[:2]
    if min(h, w) < 32:
        return None
    # YuNet mutates input size; serialize access and bound inference on large photos.
    scale = min(1.0, 1200 / max(w, h))
    small = cv2.resize(image_bgr, (max(1, round(w * scale)), max(1, round(h * scale)))) if scale < 1 else image_bgr
    with _detector_lock:
        detector = get_detector()
        detector.setInputSize((small.shape[1], small.shape[0]))
        _, faces = detector.detect(small)

    if faces is None or len(faces) == 0:
        return None

    best_face = max(faces, key=lambda f: f[2] * f[3])
    x, y, fw, fh = (float(value) for value in best_face[:4])
    sx, sy = w / small.shape[1], h / small.shape[0]
    left, top = max(0, min(w - 1, round(x * sx))), max(0, min(h - 1, round(y * sy)))
    right, bottom = max(left + 1, min(w, round((x + fw) * sx))), max(top + 1, min(h, round((y + fh) * sy)))
    nose = (float(best_face[8]) * sx, float(best_face[9]) * sy) if len(best_face) >= 10 else (
        left + (right - left) / 2, top + (bottom - top) / 2)
    return {"box": (left, top, right - left, bottom - top),
            "nose": (max(0, min(w - 1, nose[0])), max(0, min(h - 1, nose[1]))),
            "count": len(faces)}


def detect_face(image_bgr: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    result = detect_face_landmarks(image_bgr)
    return result["box"] if result is not None else None


def load_portrait(image_input) -> Image.Image:
    if isinstance(image_input, (str, Path)):
        with Image.open(image_input) as source:
            return ImageOps.exif_transpose(source).convert("RGB")
    if isinstance(image_input, Image.Image):
        return ImageOps.exif_transpose(image_input).convert("RGB")
    raise ValueError("Unsupported image input type")


def process_card_face(image_input, brightness: float = 1.2, radius: int = 170,
                      face_ratio: float = 0.32) -> Image.Image:
    """Original Colab formula: brightness, nose anchor, face width, -10px top.

    Only the detector changes (local YuNet instead of MTCNN). White padding
    replaces out-of-image transparent pixels so the old template face cannot leak.
    """
    with load_portrait(image_input) as source:
        bright = ImageEnhance.Brightness(source).enhance(brightness)
    try:
        result = detect_face_landmarks(cv2.cvtColor(np.asarray(bright), cv2.COLOR_RGB2BGR))
        width, height = bright.size
        nose_x, nose_y = result["nose"] if result else (width // 2, height // 2)
        face_width = result["box"][2] if result else width * 0.4
        scale = radius * 2 * face_ratio / max(1, face_width)
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        # Bound pathological boxes, rather than allocating a huge resized source.
        if new_size[0] * new_size[1] > 40_000_000:
            raise ValueError("Invalid face scale: inferred portrait exceeds 40 megapixels")
        with bright.resize(new_size, Image.Resampling.LANCZOS) as resized:
            left = int(nose_x * scale) - radius
            top = int(nose_y * scale) - radius - 10
            tile = Image.new("RGB", (radius * 2, radius * 2), "white")
            sx, sy = max(0, left), max(0, top)
            right, bottom = min(resized.width, left + radius * 2), min(resized.height, top + radius * 2)
            if right > sx and bottom > sy:
                with resized.crop((sx, sy, right, bottom)) as portion:
                    tile.paste(portion, (sx - left, sy - top))
            return tile
    finally:
        bright.close()

def crop_for_eclass(image_input) -> Image.Image:
    """
    原 Colab 的 10:13 最大面積裁剪，臉作錨點，不放大成近臉特寫。
    """
    with load_portrait(image_input) as image:
        w, h = image.size
        if w < 10 or h < 13:
            return ImageOps.fit(image, (10, 13), method=Image.Resampling.LANCZOS)
        box = detect_face(cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR))
        center_x, center_y = (box[0] + box[2] // 2, box[1] + box[3] // 2) if box else (w // 2, int(h * 0.4))
        # Integral units differ from Colab's floor by at most 12px, keeping exact 10:13.
        units = min(w // 10, h // 13)
        crop_w, crop_h = units * 10, units * 13
        if w / h > 10 / 13:
            left, top = center_x - crop_w // 2, 0
        else:
            left, top = 0, center_y - int(crop_h * 0.35)
        left, top = max(0, min(left, w - crop_w)), max(0, min(top, h - crop_h))
        return image.crop((left, top, left + crop_w, top + crop_h))

def remove_green_screen_to_white(img: Image.Image) -> Image.Image:
    """
    針對綠幕或非白底拍攝的照片進行智能退底，並自動填充為純白色背景。
    """
    img_rgb = img.convert("RGB")
    arr = np.array(img_rgb)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)

    lower_green = np.array([35, 43, 46])
    upper_green = np.array([85, 255, 255])
    green_mask = cv2.inRange(hsv, lower_green, upper_green)

    if np.sum(green_mask > 0) > (arr.shape[0] * arr.shape[1] * 0.05):
        kernel = np.ones((3, 3), np.uint8)
        green_mask = cv2.dilate(green_mask, kernel, iterations=1)
        green_mask = cv2.GaussianBlur(green_mask, (5, 5), 0)

        alpha = (1.0 - (green_mask.astype(float) / 255.0))[:, :, np.newaxis]
        white_bg = np.ones_like(arr, dtype=float) * 255.0
        result = (arr.astype(float) * alpha + white_bg * (1.0 - alpha)).astype(np.uint8)
        return Image.fromarray(result)

    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    rect = (int(w * 0.05), int(h * 0.05), int(w * 0.9), int(h * 0.9))

    try:
        cv2.grabCut(bgr, mask, rect, bgd_model, fgd_model, iterCount=3, mode=cv2.GC_INIT_WITH_RECT)
        fg_mask = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")
        fg_mask = cv2.GaussianBlur(fg_mask, (5, 5), 0)

        alpha = (fg_mask.astype(float) / 255.0)[:, :, np.newaxis]
        white_bg = np.ones_like(arr, dtype=float) * 255.0
        result = (arr.astype(float) * alpha + white_bg * (1.0 - alpha)).astype(np.uint8)
        return Image.fromarray(result)
    except cv2.error:
        return img_rgb