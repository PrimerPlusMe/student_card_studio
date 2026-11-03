"""Offline face location with a bundled, checksum-verified YuNet model.

Haar remains available explicitly for comparison with the validated first stage.
YuNet finds facial landmarks (including the real nose point), never identities.
"""
import hashlib
from pathlib import Path

import cv2
import numpy as np

MODEL_NAME = "face_detection_yunet_2023mar.onnx"
MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
MODEL_SOURCE = "https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet"


class FaceDetector:
    """Select the largest face and report the number of faces for manual review."""

    def __init__(self, model_path: str = "", backend: str = "yunet"):
        # "opencv" is the original phase-one name, kept for existing saved configs.
        self.backend = "haar" if backend in {"opencv", "haar"} else backend
        if self.backend == "haar":
            cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            # OpenCV's Windows filename API cannot reliably read non-ASCII paths.
            storage = cv2.FileStorage(cascade_path.read_text(encoding="utf-8"), cv2.FILE_STORAGE_READ | cv2.FILE_STORAGE_MEMORY)
            self.cascade = cv2.CascadeClassifier()
            self.cascade.read(storage.getFirstTopLevelNode())
            storage.release()
            if self.cascade.empty():
                raise RuntimeError("无法加载 Haar 离线模型，请重新安装程序。")
            self.metadata = {"backend": "haar", "model": cascade_path.name,
                             "source": "https://github.com/opencv/opencv/tree/4.x/data/haarcascades",
                             "nose": "estimated_from_face_box"}
        elif self.backend == "yunet":
            self.model_path = Path(model_path) if model_path else Path(__file__).resolve().parent.parent / "assets" / MODEL_NAME
            if not self.model_path.is_file():
                raise RuntimeError(f"找不到 YuNet 离线模型：{self.model_path}。请保留完整安装包，或重新解压程序。")
            payload = self.model_path.read_bytes()
            checksum = hashlib.sha256(payload).hexdigest()
            if checksum != MODEL_SHA256:
                raise RuntimeError("YuNet 模型完整性校验失败，文件可能损坏。请使用安装包内附的原始模型。")
            try:
                # Buffer overload works with Chinese/Unicode paths on Windows too.
                buffer = np.frombuffer(payload, dtype=np.uint8)
                self.model = cv2.FaceDetectorYN.create("onnx", buffer, np.empty(0, np.uint8), (320, 320), 0.85, 0.3, 5000)
            except cv2.error as exc:
                raise RuntimeError(f"无法初始化 YuNet 离线模型：{exc}") from exc
            self.metadata = {"backend": "yunet", "model": MODEL_NAME, "sha256": checksum,
                             "source": MODEL_SOURCE, "nose": "detected_landmark",
                             "max_detection_side": 640, "close_up_pass_side": 320}
        else:
            raise ValueError(f"未知人脸检测器：{backend}")

    def detect(self, image):
        if self.backend == "yunet":
            return self._detect_yunet(image)
        rgb = np.asarray(image.convert("RGB"))
        scale = min(1.0, 1200.0 / max(image.size))
        if scale < 1:
            rgb = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        faces = self.cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
        if not len(faces):
            return None
        face = max(faces, key=lambda box: int(box[2]) * int(box[3]))
        x, y, w, h = [float(value) / scale for value in face]
        return {"box": (x, y, w, h), "nose": (x + w * 0.5, y + h * 0.6), "count": len(faces)}

    def _detect_yunet(self, image):
        bgr = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        candidates = []
        used_shapes = set()
        # A second, smaller pass handles close-up portraits whose face is larger
        # than YuNet's training range in the first pass. NMS removes duplicates.
        for limit in (640, 320):
            scale = min(1.0, limit / max(image.size))
            width, height = max(1, round(image.width * scale)), max(1, round(image.height * scale))
            shape = (width, height)
            if shape in used_shapes:
                continue
            used_shapes.add(shape)
            frame = cv2.resize(bgr, shape, interpolation=cv2.INTER_AREA) if scale < 1 else bgr
            # Tiny inputs must not produce an invalid DNN tensor.
            frame = cv2.copyMakeBorder(frame, 0, max(0, 32 - height), 0, max(0, 32 - width), cv2.BORDER_CONSTANT, value=(255, 255, 255))
            self.model.setInputSize((frame.shape[1], frame.shape[0]))
            _, faces = self.model.detect(frame)
            if faces is None:
                continue
            for face in faces:
                x, y, width_f, height_f = [float(value) / scale for value in face[:4]]
                if width_f <= 0 or height_f <= 0:
                    continue
                candidates.append({"box": (x, y, width_f, height_f),
                                   "nose": (float(face[8]) / scale, float(face[9]) / scale),
                                   "score": float(face[14])})
        if not candidates:
            return None
        kept = cv2.dnn.NMSBoxes([face["box"] for face in candidates], [face["score"] for face in candidates], 0.85, 0.3)
        faces = [candidates[int(index)] for index in np.asarray(kept).reshape(-1)]
        if not faces:
            return None
        face = max(faces, key=lambda value: value["box"][2] * value["box"][3])
        return {**face, "count": len(faces)}
