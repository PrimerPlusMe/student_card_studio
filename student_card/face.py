"""
Face detection, eClass alignment/cropping, and background matting utilities.
"""
from pathlib import Path
from typing import Optional, Tuple
import os
import cv2
import numpy as np
from PIL import Image

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
MODEL_PATH = PROJECT_ROOT / "assets" / "face_detection_yunet_2023mar.onnx"

_detector = None

def get_detector():
    """Lazy load cv2.FaceDetectorYN model."""
    global _detector
    if _detector is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"YuNet model not found at {MODEL_PATH}")
        _detector = cv2.FaceDetectorYN.create(
            model=str(MODEL_PATH),
            config="",
            input_size=(320, 320),
            score_threshold=0.6,
            nms_threshold=0.3,
            top_k=5000,
            backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
            target_id=cv2.dnn.DNN_TARGET_CPU,
        )
    return _detector

def detect_face(image_bgr: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    detector = get_detector()
    h, w = image_bgr.shape[:2]
    detector.setInputSize((w, h))
    _, faces = detector.detect(image_bgr)

    if faces is None or len(faces) == 0:
        return None

    best_face = max(faces, key=lambda f: f[2] * f[3])
    x, y, fw, fh = map(int, best_face[:4])
    return x, y, fw, fh

def crop_for_eclass(image_input) -> Image.Image:
    """
    依照 eClass 標準規格（3:4 比例，居中對齊面部與肩部）進行裁切。
    """
    if isinstance(image_input, (str, Path)):
        img_bgr = cv2.imread(str(image_input))
        if img_bgr is None:
            pil_img = Image.open(str(image_input)).convert("RGB")
            img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    elif isinstance(image_input, Image.Image):
        img_bgr = cv2.cvtColor(np.array(image_input.convert("RGB")), cv2.COLOR_RGB2BGR)
    else:
        raise ValueError("Unsupported image input type")

    h, w = img_bgr.shape[:2]
    face_box = detect_face(img_bgr)
    target_aspect = 3.0 / 4.0

    if face_box is not None:
        fx, fy, fw, fh = face_box
        center_x = fx + fw // 2
        center_y = fy + int(fh * 0.45)

        crop_h = int(fh * 2.2)
        crop_w = int(crop_h * target_aspect)
        crop_w = min(crop_w, w)
        crop_h = min(crop_h, h)

        x1 = max(0, center_x - crop_w // 2)
        y1 = max(0, center_y - int(crop_h * 0.38))
        x2 = min(w, x1 + crop_w)
        y2 = min(h, y1 + crop_h)

        if x2 - x1 < crop_w and x1 > 0:
            x1 = max(0, x2 - crop_w)
        if y2 - y1 < crop_h and y1 > 0:
            y1 = max(0, y2 - crop_h)

        cropped = img_bgr[y1:y2, x1:x2]
    else:
        if w / h > target_aspect:
            new_w = int(h * target_aspect)
            x1 = (w - new_w) // 2
            cropped = img_bgr[:, x1 : x1 + new_w]
        else:
            new_h = int(w / target_aspect)
            y1 = (h - new_h) // 2
            cropped = img_bgr[y1 : y1 + new_h, :]

    cropped_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
    return Image.fromarray(cropped_rgb)

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
        return Image.fromarray(result, "RGB")

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
        return Image.fromarray(result, "RGB")
    except Exception:
        return img_rgb