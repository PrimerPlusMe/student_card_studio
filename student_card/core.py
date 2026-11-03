"""Offline processing engine, independent from the desktop interface.

Original notebook layout/cropping parameters are retained in reference pixels.
Every run writes into a newly created directory and leaves all inputs unchanged.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import sys
import uuid
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable

import barcode
import img2pdf
import openpyxl
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from .face import FaceDetector

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
PATH_KEYS = ("excel_path", "photo_path", "template_path", "mask_path", "back_path", "font_eng_path", "font_chi_path", "font_id_path", "output_dir", "pdf_input_dir", "model_path")
MODES = {"cards", "pdf", "crop"}


def default_config() -> dict:
    config = dict.fromkeys(PATH_KEYS, "")
    config.update(brightness=1.15, face_ratio=0.32, photo_offset_y=0,
                  center_x=324, photo_x=155, photo_y=347, face_radius=170,
                  eng_only_y=768, eng_dual_y=742, chi_dual_y=812,
                  eng_font_size=46, chi_font_size=65, id_font_size=42,
                  barcode_width=350, barcode_height=90, barcode_bottom_y=953,
                  id_text_top_y=960, reference_width=648, reference_height=1050,
                  pdf_width_mm=54.0, pdf_height_mm=85.6,
                  make_pdf=True, make_zip=True, detector="yunet",
                  column_id="學號", column_eng="Name", column_chi="姓名")
    return config


def _config(values):
    config = default_config()
    config.update(values)
    return config


def find_font(kind="eng") -> str:
    """Use local OS fonts without redistributing proprietary fonts."""
    win = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    choices = {
        "eng": [win / "arialbd.ttf", win / "arial.ttf", Path("/System/Library/Fonts/Supplemental/Arial.ttf")],
        "chi": [win / "msyh.ttc", win / "simkai.ttf", win / "simsun.ttc", Path("/System/Library/Fonts/PingFang.ttc"), Path("/System/Library/Fonts/Supplemental/Songti.ttc"), Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")],
        "id": [win / "arial.ttf", Path("/System/Library/Fonts/Supplemental/Arial.ttf")],
    }
    choices[kind] += [Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    for candidate in choices[kind]:
        if candidate.is_file():
            return str(candidate)
    return ""


def _font_path(config, kind):
    return config.get(f"font_{kind}_path") or find_font(kind)


def _text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _student_id(cell):
    value = cell.value
    text = _text(value)
    # Excel numeric cells may encode leading zeroes through a simple custom format.
    if isinstance(value, (int, float)) and not isinstance(value, bool) and re.fullmatch(r"0+", cell.number_format or ""):
        if float(value).is_integer():
            return str(int(value)).zfill(len(cell.number_format))
    return text


def _safe_id(value):
    return bool(value and value not in {".", ".."} and re.fullmatch(r"[A-Za-z0-9_-]+", value))


class PhotoSource:
    """Index directories or read ZIP members in memory, never extract archive paths."""

    def __init__(self, path):
        self.path = Path(path)
        self.archive = None
        self.photos = []
        self.errors = []
        self.warnings = []
        self.by_id = defaultdict(list)
        if self.path.is_dir():
            for file in sorted(self.path.rglob("*"), key=lambda p: str(p).casefold()):
                if not file.is_file() or self._ignored(file.parts) or file.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                # Do not follow a directory symlink outside the supplied folder.
                if not file.resolve().is_relative_to(self.path.resolve()):
                    self.warnings.append(f"已忽略目录外的链接：{file.name}")
                    continue
                item = {"key": str(file), "name": file.name, "stem": file.stem, "relative": str(file.relative_to(self.path))}
                self.photos.append(item)
        elif self.path.is_file() and self.path.suffix.lower() == ".zip":
            self.archive = zipfile.ZipFile(self.path)
            total = 0
            for info in sorted(self.archive.infolist(), key=lambda p: p.filename.casefold()):
                clean = info.filename.replace("\\", "/")
                name = PurePosixPath(clean)
                if info.is_dir() or self._ignored(name.parts):
                    continue
                if name.is_absolute() or ".." in name.parts or re.match(r"^[A-Za-z]:", clean):
                    self.errors.append(f"ZIP 包含不安全路径：{info.filename}")
                    continue
                if name.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                total += info.file_size
                if info.file_size > 100 * 1024 * 1024 or total > 2 * 1024 ** 3:
                    self.errors.append("ZIP 图片展开体积超过限制（单图 100MB，总计 2GB）。")
                    break
                item = {"key": info.filename, "name": name.name, "stem": name.stem, "relative": str(name)}
                self.photos.append(item)
        else:
            raise ValueError("请选择存在的照片文件夹或 ZIP 文件。")
        for item in self.photos:
            self.by_id[item["stem"].casefold()].append(item)

    @staticmethod
    def _ignored(parts):
        return any(part == "__MACOSX" or part.startswith("._") or part.startswith(".") for part in parts if part not in {".", ".."})

    def open(self, item):
        source = io.BytesIO(self.archive.read(item["key"])) if self.archive else item["key"]
        with Image.open(source) as raw:
            raw.load()
            image = ImageOps.exif_transpose(raw)
            if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                rgba = image.convert("RGBA")
                opaque = Image.new("RGBA", rgba.size, "white")
                opaque.alpha_composite(rgba)
                return opaque.convert("RGB")
            return image.convert("RGB")

    def close(self):
        if self.archive:
            self.archive.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _read_students(config):
    workbook = openpyxl.load_workbook(config["excel_path"], read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows = sheet.iter_rows()
        header = next(rows, ())
        names = [_text(cell.value) for cell in header]
        id_column = config["column_id"].strip()
        eng_column = config["column_eng"].strip()
        chi_column = config["column_chi"].strip()
        required = [id_column, eng_column] + ([chi_column] if chi_column else [])
        missing = [name for name in required if not name or name not in names]
        if missing:
            raise ValueError(f"Excel 缺少列：{', '.join(missing)}；实际列名：{', '.join(names)}")
        for name in required:
            if names.count(name) > 1:
                raise ValueError(f"Excel 列名重复：{name}")
        id_index, eng_index = names.index(id_column), names.index(eng_column)
        chi_index = names.index(chi_column) if chi_column else None
        students = []
        for number, cells in enumerate(rows, 2):
            if not any(cell.value is not None and _text(cell.value) for cell in cells):
                continue
            student_id = _student_id(cells[id_index])
            english = _text(cells[eng_index].value)
            chinese = _text(cells[chi_index].value) if chi_index is not None else ""
            if chinese in {"/", "／", "nan", "NaN"}:
                chinese = ""
            issues = []
            if not student_id:
                issues.append("学号为空")
            elif not _safe_id(student_id):
                issues.append("学号仅支持英文字母、数字、下划线和连字符")
            if not english and not chinese:
                issues.append("姓名为空")
            students.append({"student_id": student_id, "english_name": english, "chinese_name": chinese, "photo": "", "issues": issues, "row": number})
        counts = Counter(row["student_id"].casefold() for row in students if row["student_id"])
        for row in students:
            if counts[row["student_id"].casefold()] > 1:
                row["issues"].append("名单中学号重复")
        return students
    finally:
        workbook.close()


def _validate_parameters(config, errors):
    positive = ("face_radius", "face_ratio", "eng_font_size", "chi_font_size", "id_font_size", "barcode_width", "barcode_height", "reference_width", "reference_height", "pdf_width_mm", "pdf_height_mm")
    for key in positive:
        try:
            if not math.isfinite(float(config[key])) or float(config[key]) <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            errors.append(f"参数 {key} 必须是大于 0 的数值。")
    try:
        if not 0.1 <= float(config["brightness"]) <= 3:
            errors.append("照片亮度应在 0.1 到 3 之间。")
    except (ValueError, TypeError):
        errors.append("照片亮度必须是数值。")


def inspect_inputs(config: dict, mode: str = "cards") -> dict:
    config = _config(config)
    errors, warnings, students = [], [], []
    photo_count = 0
    if mode not in MODES:
        return {"ok": False, "errors": ["未知任务类型。"], "warnings": [], "students": [], "photo_count": 0}
    _validate_parameters(config, errors)
    output = str(config.get("output_dir", "")).strip()
    if not output:
        errors.append("请选择输出文件夹。")
    elif Path(output).exists() and not Path(output).is_dir():
        errors.append("输出路径必须是文件夹。")
    elif mode in {"cards", "crop"} and config["photo_path"] and Path(config["photo_path"]).is_dir():
        if Path(output).resolve().is_relative_to(Path(config["photo_path"]).resolve()):
            errors.append("输出文件夹不能位于输入照片文件夹内，请选择独立位置，避免再次处理历史结果。")
    elif mode == "pdf" and config["pdf_input_dir"] and Path(config["pdf_input_dir"]).is_dir():
        if Path(output).resolve().is_relative_to(Path(config["pdf_input_dir"]).resolve()):
            errors.append("输出文件夹不能位于正面图片文件夹内，请选择独立位置，避免再次处理历史结果。")
    for key, label in (("template_path", "正面底图"), ("mask_path", "照片遮罩")) if mode == "cards" else []:
        try:
            with Image.open(config[key]) as image:
                image.verify()
        except Exception as exc:
            errors.append(f"{label}无法读取：{exc}")
    if mode == "cards" and not errors:
        with Image.open(config["template_path"]) as template, Image.open(config["mask_path"]) as mask:
            if template.size != mask.size:
                errors.append(f"底图尺寸 {template.size} 与遮罩尺寸 {mask.size} 不一致。")
            if mask.convert("L").getextrema() == (0, 0):
                errors.append("遮罩全黑，没有可放置照片的区域。")
            if mask.convert("L").getextrema() == (255, 255):
                warnings.append("遮罩全白，会用照片画布覆盖整张底图，请确认。")
            if abs(template.width / template.height - float(config["pdf_width_mm"]) / float(config["pdf_height_mm"])) > 0.015:
                warnings.append("底图宽高比与 PDF 实际尺寸不同，PDF 会等比居中并留白；请核对打印尺寸。")
    if mode == "pdf" or (mode == "cards" and config["make_pdf"]):
        try:
            with Image.open(config["back_path"]) as back:
                back.verify()
        except Exception as exc:
            errors.append(f"背面底图无法读取：{exc}")
    if mode == "cards":
        for kind, label in (("eng", "英文"), ("chi", "中文"), ("id", "学号")):
            try:
                ImageFont.truetype(_font_path(config, kind), 20)
            except Exception:
                errors.append(f"找不到可用的{label}字体，请选择 TTF / TTC / OTF 字体。")
        try:
            students = _read_students(config)
            if not students:
                errors.append("Excel 中没有学生记录。")
        except Exception as exc:
            errors.append(f"读取学生名单失败：{exc}")
    if mode in {"cards", "crop"}:
        try:
            FaceDetector(config["model_path"], config["detector"])
        except Exception as exc:
            errors.append(f"人脸检测器不可用：{exc}")
        try:
            with PhotoSource(config["photo_path"]) as source:
                photo_count = len(source.photos)
                errors.extend(source.errors)
                warnings.extend(source.warnings)
                if not photo_count:
                    errors.append("照片来源中没有支持的图片。")
                for row in students:
                    candidates = source.by_id.get(row["student_id"].casefold(), [])
                    if not candidates:
                        row["issues"].append("缺少同学号照片")
                    elif len(candidates) > 1:
                        row["issues"].append("同学号匹配到多张照片")
                    else:
                        row["photo"] = candidates[0]["key"]
                        try:
                            source.open(candidates[0])
                        except Exception as exc:
                            row["issues"].append(f"照片损坏或无法读取：{exc}")
                if mode == "crop":
                    students = [{"student_id": p["stem"], "english_name": "", "chinese_name": "", "photo": p["key"], "issues": [], "row": n + 1} for n, p in enumerate(source.photos)]
        except Exception as exc:
            errors.append(f"读取照片来源失败：{exc}")
    if mode == "pdf":
        folder = Path(config["pdf_input_dir"])
        if not config["pdf_input_dir"] or not folder.is_dir():
            errors.append("请选择学生证正面图片文件夹。")
        else:
            photos = _pdf_images(folder)
            photo_count = len(photos)
            if not photos:
                errors.append("正面图片文件夹中没有 PNG/JPEG 图片。")
            students = [{"student_id": p.stem, "english_name": "", "chinese_name": "", "photo": str(p), "issues": [], "row": n + 1} for n, p in enumerate(photos)]
    invalid = sum(bool(row["issues"]) for row in students)
    if invalid:
        warnings.append(f"{invalid} 条记录有输入问题，将跳过；请查看学生明细。")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "students": students, "photo_count": photo_count}


def _pdf_images(folder):
    return sorted((p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"} and not PhotoSource._ignored(p.relative_to(folder).parts)), key=lambda p: (p.name.casefold(), str(p)))


def _face_image(image, config, detector):
    image = ImageEnhance.Brightness(image).enhance(float(config["brightness"]))
    face = detector.detect(image)
    notes = []
    if face is None:
        nose_x, nose_y = image.width / 2, image.height / 2
        face_width = image.width * 0.4
        notes.append("未检测到人脸，已按中心回退裁剪，请人工复核")
    else:
        nose_x, nose_y = face["nose"]
        face_width = max(1, face["box"][2])
        if face["count"] > 1:
            notes.append(f"检测到 {face['count']} 张人脸，已选择最大人脸，请人工复核")
    radius = max(1, int(config["face_radius"]))
    scale = radius * 2 * float(config["face_ratio"]) / face_width
    # Limit pathological face boxes from allocating huge intermediate bitmaps.
    new_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    if max(new_size) > 20000:
        raise ValueError("照片缩放尺寸过大，请调整人脸比例。")
    resized = image.resize(new_size, Image.Resampling.LANCZOS)
    left = round(nose_x * scale - radius)
    top = round(nose_y * scale - radius - 10 - float(config["photo_offset_y"]))
    # White padding, never transparent/black when the crop crosses image borders.
    result = Image.new("RGB", (radius * 2, radius * 2), "white")
    result.paste(resized, (-left, -top))
    return result, notes


def _fitted_font(path, size, text, max_width, draw):
    size = max(6, round(size))
    font = ImageFont.truetype(path, size)
    while size > 6 and draw.textlength(text, font=font) > max_width:
        size -= 1
        font = ImageFont.truetype(path, size)
    if draw.textlength(text, font=font) > max_width:
        raise ValueError("姓名或学号过长，最小字号仍超出可用区域。")
    return font


def _barcode_image(student_id, width, height):
    """Rasterize Code128 with integral module width and >=10-module quiet zones."""
    bits = barcode.get_barcode_class("code128")(student_id).build()[0]
    modules = len(bits) + 20
    unit = width // modules
    if unit < 1:
        raise ValueError("学号过长，当前条码宽度不足；请增加条码宽度。")
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    start = (width - len(bits) * unit) // 2
    for index, bit in enumerate(bits):
        if bit == "1":
            x = start + index * unit
            draw.rectangle((x, 0, x + unit - 1, height - 1), fill="black")
    return image


def _render_card(config, row, source, detector, template=None, mask=None):
    if template is None:
        with Image.open(config["template_path"]) as raw:
            template = raw.convert("RGB")
    if mask is None:
        with Image.open(config["mask_path"]) as raw:
            mask = raw.convert("L")
    candidates = source.by_id.get(row["student_id"].casefold(), [])
    if len(candidates) != 1:
        raise ValueError("该学生照片缺失或同学号有多张照片。")
    photo = source.open(candidates[0])
    face, notes = _face_image(photo, config, detector)
    sx = template.width / float(config["reference_width"])
    sy = template.height / float(config["reference_height"])
    bg = template.copy()
    face_canvas = Image.new("RGB", template.size, "white")
    target = (max(1, round(face.width * sx)), max(1, round(face.height * sy)))
    face_canvas.paste(face.resize(target, Image.Resampling.LANCZOS), (round(float(config["photo_x"]) * sx), round(float(config["photo_y"]) * sy)))
    bg = Image.composite(face_canvas, bg, mask)
    draw = ImageDraw.Draw(bg)
    center = float(config["center_x"]) * sx
    max_width = max(1, min(center, template.width - center) * 2 - 32 * sx)
    eng = _fitted_font(_font_path(config, "eng"), float(config["eng_font_size"]) * min(sx, sy), row["english_name"], max_width, draw)
    if row["chinese_name"]:
        chi = _fitted_font(_font_path(config, "chi"), float(config["chi_font_size"]) * min(sx, sy), row["chinese_name"], max_width, draw)
        draw.text((center, float(config["eng_dual_y"]) * sy), row["english_name"], fill="black", font=eng, anchor="mm")
        draw.text((center, float(config["chi_dual_y"]) * sy), row["chinese_name"], fill="black", font=chi, anchor="mm")
    else:
        draw.text((center, float(config["eng_only_y"]) * sy), row["english_name"], fill="black", font=eng, anchor="mm")
    width, height = max(1, round(float(config["barcode_width"]) * sx)), max(1, round(float(config["barcode_height"]) * sy))
    code = _barcode_image(row["student_id"], width, height)
    x, y = round(center - width / 2), round(float(config["barcode_bottom_y"]) * sy - height)
    if x < 0 or y < 0 or x + width > bg.width or y + height > bg.height:
        raise ValueError("条码区域超出底图，请调整条码位置和大小。")
    bg.paste(code, (x, y))
    id_font = _fitted_font(_font_path(config, "id"), float(config["id_font_size"]) * min(sx, sy), row["student_id"], max_width, draw)
    draw.text((center, float(config["id_text_top_y"]) * sy), row["student_id"], fill="black", font=id_font, anchor="mt")
    return bg, notes


def preview_card(config, student_id=None):
    config = _config(config)
    report = inspect_inputs(config, "cards")
    if not report["ok"]:
        raise ValueError("\n".join(report["errors"]))
    rows = [row for row in report["students"] if (student_id is None or row["student_id"] == student_id) and not row["issues"]]
    if not rows:
        raise ValueError("没有可预览的学生，请先修正输入问题。")
    with PhotoSource(config["photo_path"]) as source:
        image, notes = _render_card(config, rows[0], source, FaceDetector(config["model_path"], config["detector"]))
        image.info["review_notes"] = notes
        return image


def _write_pdf(front_path, back_path, destination, config):
    layout = img2pdf.get_layout_fun(pagesize=(img2pdf.mm_to_pt(float(config["pdf_width_mm"])), img2pdf.mm_to_pt(float(config["pdf_height_mm"]))), fit=img2pdf.FitMode.into)
    with destination.open("wb") as output:
        img2pdf.convert(str(front_path), str(back_path), layout_fun=layout, outputstream=output)


def _normalized_png(path, destination):
    with Image.open(path) as raw:
        image = ImageOps.exif_transpose(raw)
        if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
            rgba = image.convert("RGBA")
            white = Image.new("RGBA", rgba.size, "white")
            white.alpha_composite(rgba)
            image = white.convert("RGB")
        else:
            image = image.convert("RGB")
        image.save(destination)


def _crop_image(image, detector):
    face = detector.detect(image)
    notes = []
    if face is None:
        center_x, center_y = image.width / 2, image.height * 0.4
        notes.append("未检测到人脸，已按上方 40% 回退定位，请人工复核")
    else:
        x, y, width, height = face["box"]
        center_x, center_y = x + width / 2, y + height / 2
        if face["count"] > 1:
            notes.append(f"检测到 {face['count']} 张人脸，已选择最大人脸，请人工复核")
    # Exact 10:13 integer ratio; round down by at most 12 source pixels.
    unit = min(image.width // 10, image.height // 13)
    if unit < 1:
        raise ValueError("照片太小，至少需要 10×13 像素。")
    width, height = 10 * unit, 13 * unit
    left = min(max(0, round(center_x - width / 2)), image.width - width)
    top = 0 if image.width / image.height > 10 / 13 else round(center_y - height * 0.35)
    top = min(max(0, top), image.height - height)
    return image.crop((left, top, left + width, top + height)), notes


def _new_output(config, mode):
    root = Path(config["output_dir"]).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    name = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + mode + "_" + uuid.uuid4().hex[:6]
    output = root / name
    output.mkdir(exist_ok=False)
    return output


def _csv_safe(value):
    value = str(value)
    # Prevent spreadsheet formulas when a CSV detail is opened in Excel.
    return "'" + value if value.startswith(("=", "+", "-", "@")) else value


def _write_reports(output, config, mode, results, summary):
    fields = ["row", "student_id", "english_name", "chinese_name", "status", "message", "source", "output"]
    with (output / "processing_report.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in results:
            writer.writerow({key: _csv_safe(row.get(key, "")) for key in fields})
    manifest = {"app_version": "1.0.0", "mode": mode, "created_at": datetime.now().astimezone().isoformat(), "summary": summary, "config": config, "records": results}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if config["make_zip"]:
        with zipfile.ZipFile(output / "results.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(output.rglob("*")):
                if file.is_file() and file.name != "results.zip" and not file.name.startswith(".working"):
                    archive.write(file, str(file.relative_to(output)))


def run_job(config: dict, mode="cards", progress: Callable | None = None, cancelled: Callable | None = None) -> dict:
    config = _config(config)
    progress = progress or (lambda percent, message: None)
    cancelled = cancelled or (lambda: False)
    progress(0, "正在检查输入资料…")
    report = inspect_inputs(config, mode)
    if not report["ok"]:
        raise ValueError("\n".join(report["errors"]))
    output = _new_output(config, mode)
    summary = {"output_dir": str(output), "success": 0, "failed": 0, "skipped": 0, "review": 0, "cancelled": False}
    results = []
    source = None
    pdf_paths = []
    try:
        rows = report["students"]
        detector = FaceDetector(config["model_path"], config["detector"]) if mode in {"cards", "crop"} else None
        if detector:
            summary["detector"] = detector.metadata
        if mode in {"cards", "crop"}:
            source = PhotoSource(config["photo_path"])
        if mode == "cards":
            png_folder = output / "cards_png"
            png_folder.mkdir()
            with Image.open(config["template_path"]) as raw:
                template = raw.convert("RGB")
            with Image.open(config["mask_path"]) as raw:
                mask = raw.convert("L")
        if mode in {"cards", "pdf"} and (mode == "pdf" or config["make_pdf"]):
            pdf_folder = output / "cards_pdf"
            pdf_folder.mkdir()
            back_file = output / ".working_back.png"
            _normalized_png(config["back_path"], back_file)
        if mode == "crop":
            crop_folder = output / "eclass_photos"
            crop_folder.mkdir()
        for index, row in enumerate(rows):
            if cancelled():
                summary["cancelled"] = True
                for remaining in rows[index:]:
                    results.append({**remaining, "status": "cancelled", "message": "用户取消，尚未处理", "source": remaining["photo"], "output": ""})
                break
            result = {**row, "status": "", "message": "", "source": row["photo"], "output": ""}
            if row["issues"]:
                result.update(status="skipped", message="；".join(row["issues"]))
                summary["skipped"] += 1
            else:
                try:
                    notes = []
                    if mode == "cards":
                        card, notes = _render_card(config, row, source, detector, template, mask)
                        file = png_folder / (row["student_id"] + "_ID.png")
                        card.save(file, dpi=(300, 300))
                        result["output"] = str(file.relative_to(output))
                        if config["make_pdf"]:
                            pdf = pdf_folder / (row["student_id"] + "_ID.pdf")
                            _write_pdf(file, back_file, pdf, config)
                            pdf_paths.append(pdf)
                    elif mode == "crop":
                        item = source.photos[index]
                        cropped, notes = _crop_image(source.open(item), detector)
                        relative = Path(item["relative"])
                        # Preserve subfolders so equal basenames never overwrite.
                        file = crop_folder / relative.with_suffix(".jpg")
                        if file.exists():
                            file = file.with_name(file.stem + "_" + str(index + 1) + file.suffix)
                        file.parent.mkdir(parents=True, exist_ok=True)
                        cropped.save(file, quality=95, dpi=(300, 300))
                        result["output"] = str(file.relative_to(output))
                    else:
                        # Prefix with the index if duplicate stems are present.
                        stem = Path(row["photo"]).stem
                        file = pdf_folder / (stem + ".pdf")
                        if file.exists():
                            file = pdf_folder / (f"{index + 1:05d}_" + stem + ".pdf")
                        front_file = output / ".working_front.png"
                        _normalized_png(row["photo"], front_file)
                        _write_pdf(front_file, back_file, file, config)
                        pdf_paths.append(file)
                        result["output"] = str(file.relative_to(output))
                    result.update(status="review" if notes else "success", message="；".join(notes) or "完成")
                    summary["success"] += 1
                    if notes:
                        summary["review"] += 1
                except Exception as exc:
                    result.update(status="failed", message=str(exc))
                    summary["failed"] += 1
            results.append(result)
            progress(round((index + 1) / max(1, len(rows)) * 90), f"{index + 1}/{len(rows)}  {row['student_id']}  {result['message']}")
        if pdf_paths and not cancelled():
            progress(93, "正在生成全班合并 PDF…")
            from pypdf import PdfWriter
            writer = PdfWriter()
            try:
                for pdf in sorted(pdf_paths, key=lambda p: p.name.casefold()):
                    writer.append(str(pdf))
                with (output / "All_Students_Combined.pdf").open("wb") as handle:
                    writer.write(handle)
            finally:
                writer.close()
        elif cancelled():
            summary["cancelled"] = True
    except Exception as exc:
        # Keep a machine-readable report even when a fatal backend error occurs.
        summary["fatal_error"] = str(exc)
        summary["failed"] += 1
        raise
    finally:
        if source:
            source.close()
        for name in (".working_back.png", ".working_front.png"):
            (output / name).unlink(missing_ok=True)
        _write_reports(output, config, mode, results, summary)
    progress(100, "任务已取消，已保留完成的文件和明细。" if summary["cancelled"] else "处理完成。请查看需复核及失败记录。")
    return summary


def create_demo(destination):
    from .demo import create_demo as generate
    return generate(destination)
