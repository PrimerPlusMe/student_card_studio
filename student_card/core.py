"""Offline school cards, eClass crops, review and individual/combined PDFs."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from io import BytesIO
from itertools import islice
from pathlib import Path
import math
import re
from tempfile import TemporaryDirectory
from typing import Callable, Iterable, Optional, Union
from uuid import uuid4

from openpyxl import load_workbook
from barcode import Code128
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont, ImageOps

from student_card.face import crop_for_eclass, get_detector, process_card_face, remove_green_screen_to_white
from student_card.pdf import create_student_pdf, merge_student_pdfs, pdf_image, validate_page_size

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ProgressCallback = Optional[Callable[[int, int, str], None]]
CardSource = Union[Image.Image, str, Path]
COLUMN_ALIASES = {
    "student_id": ("StudentID", "學號", "学号", "ID"),
    "name": ("Name", "姓名"),
    "english_name": ("Name", "EnglishName", "英文姓名"),
    "chinese_name": ("姓名", "中文姓名"),
    "class_name": ("Class", "班別", "班别"),
    "class_number": ("ClassNumber", "學號/班號", "ClassNo", "班號", "班号"),
}


@dataclass
class ProcessStats:
    total: int = 0
    success: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    output_dir: str = ""
    review_pdf: str = ""
    individual_pdf_dir: str = ""
    combined_pdf: str = ""
    pdf_success: int = 0
    pdf_failed: int = 0


def clean_str(value) -> str:
    """Preserve textual IDs exactly; only normalize genuine numeric values."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _cell_text(cell) -> str:
    if cell.data_type == "f":
        raise ValueError("公式欄位請先轉為值 / Convert formula cells to values first")
    if cell.data_type == "e":
        raise ValueError(f"Excel 儲存格錯誤 / Cell error: {cell.value}")
    value = cell.value
    text = clean_str(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and text:
        if re.fullmatch(r"0+", cell.number_format or "") and float(value).is_integer():
            return text.zfill(len(cell.number_format))
    return text


def read_students(excel_path: Union[str, Path]) -> list[dict]:
    """Read the first worksheet without numeric inference on textual IDs."""
    path = Path(excel_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"找不到名冊 / Student list not found: {path}")
    if path.suffix.lower() != ".xlsx":
        raise ValueError("名冊必須是 .xlsx / Student list must be an .xlsx file")
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        rows = workbook.worksheets[0].iter_rows()
        header = next(rows, ())
        headers = [clean_str(cell.value).casefold() for cell in header]
        indices = {
            key: [i for alias in aliases for i, title in enumerate(headers) if title == alias.casefold()]
            for key, aliases in COLUMN_ALIASES.items()
        }
        for key in ("student_id", "name"):
            if not indices[key]:
                raise ValueError(f"缺少必要欄位 / Missing required column: {' / '.join(COLUMN_ALIASES[key])}")
        students = []
        for number, cells in enumerate(rows, 2):
            if not any(clean_str(cell.value) for cell in cells):
                continue
            student = {"row": number, "issues": []}
            for key, positions in indices.items():
                student[key] = ""
                for position in positions:
                    if position >= len(cells):
                        continue
                    try:
                        text = _cell_text(cells[position])
                    except ValueError as exc:
                        student["issues"].append(str(exc))
                        continue
                    if text:
                        student[key] = text
                        break
            students.append(student)
        if not students:
            raise ValueError("名冊沒有學生資料 / Student list is empty")
        return students
    finally:
        workbook.close()


def _safe_component(text: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", text).strip(" .")
    # Filesystem limits count bytes, not Chinese/Unicode characters.
    text = text.encode("utf-8")[:64].decode("utf-8", errors="ignore").rstrip(" .")
    if not text:
        return "_"
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", text):
        text = "_" + text
    return text


def _photo_source(photos_dir: str, output_dir: str) -> tuple[Path, Path, list[Path]]:
    if not str(photos_dir).strip() or not str(output_dir).strip():
        raise ValueError("請指定相片和輸出目錄 / Specify photo and output directories")
    source = Path(photos_dir).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    if not source.is_dir():
        raise NotADirectoryError(f"相片目錄不存在 / Photo directory not found: {source}")
    if destination == source or source in destination.parents:
        raise ValueError("輸出不可位於相片目錄內 / Output must be outside the photo directory")
    files = sorted((p for p in source.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS),
                   key=lambda p: p.name.casefold())
    if not files:
        raise ValueError("相片目錄沒有 JPG/PNG / No JPG/PNG photos found")
    return source, destination, files


def _new_output(destination: Path, mode: str) -> Path:
    output = destination / f"{mode}_{datetime.now():%Y%m%d_%H%M%S_%f}_{uuid4().hex[:6]}"
    output.mkdir(parents=True, exist_ok=False)
    return output


@lru_cache(maxsize=128)
def get_font(font_path: Optional[str], size: int) -> ImageFont.ImageFont:
    if font_path:
        return ImageFont.truetype(str(Path(font_path).expanduser()), max(1, size))
    candidates = [font_path] if font_path else []
    candidates.extend([
        "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Light.ttc",
        "C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/simsun.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, max(1, size))
            except OSError:
                continue
    return ImageFont.load_default(size=max(1, size))


def _draw_fitted(draw, position, text, font_path, size, width, anchor="mm"):
    low, high = 1, max(1, size)
    while low < high:
        middle = (low + high + 1) // 2
        if draw.textlength(text, font=get_font(font_path, middle)) <= width:
            low = middle
        else:
            high = middle - 1
    draw.text(position, text, fill="black", font=get_font(font_path, low), anchor=anchor)


def _school_assets(front_template: str, mask_path: str = "", font_eng_path: str = "",
                   font_chi_path: str = "", font_id_path: str = "") -> dict:
    """Use explicit resources, or original Colab filenames beside the template."""
    parent = Path(front_template).expanduser().resolve().parent
    result = {}
    for key, explicit, filename in (
        ("mask_path", mask_path, "psd_mask.png"),
        ("font_eng_path", font_eng_path, "ARLRDBD.TTF"),
        ("font_chi_path", font_chi_path, "BiauKai.ttf"),
        ("font_id_path", font_id_path, "Arial.ttf"),
    ):
        candidate = Path(explicit).expanduser().resolve() if explicit else parent / filename
        if explicit or candidate.is_file():
            if not candidate.is_file():
                raise FileNotFoundError(f"找不到製卡資源 / Card resource not found: {candidate}")
            result[key] = str(candidate)
        else:
            result[key] = ""
    if not result["mask_path"]:
        raise ValueError("需要原廠照片遮罩 / Select psd_mask.png (same size as the template)")
    for key, size in (("font_eng_path", 46), ("font_chi_path", 65), ("font_id_path", 42)):
        get_font(result[key] or None, size)
    return result


def _load_mask(path: str, template_size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        if source.size != template_size:
            raise ValueError("遮罩與模板尺寸不一致 / Mask must have the same dimensions as the template")
        mask = source.convert("L")
    bbox = mask.getbbox()
    if bbox is None or bbox == (0, 0, mask.width, mask.height):
        mask.close()
        raise ValueError("照片遮罩必須只覆蓋照片區 / Mask must isolate the portrait region")
    # Fixed school coordinates are intentionally NOT scaled to unrelated templates.
    if bbox[0] < 155 or bbox[1] < 347 or bbox[2] > 495 or bbox[3] > 687:
        mask.close()
        raise ValueError("遮罩不符合原 Colab 照片區 / Mask must fit x=155..495, y=347..687")
    return mask


def _barcode_image(student_id: str) -> Image.Image:
    code = Code128(student_id, writer=ImageWriter())
    pattern = code.build()[0]
    if len(pattern) > 130:
        # Avoid fractional-module resampling on longer IDs. Include 10-module
        # quiet zones and draw an integral width per module within Colab's box.
        module_width = 350 // (len(pattern) + 20)
        if module_width < 1:
            raise ValueError("學號太長，條碼無法放入原版區域 / ID barcode is too long for the layout")
        image = Image.new("RGB", (350, 90), "white")
        draw = ImageDraw.Draw(image)
        left = (350 - len(pattern) * module_width) // 2
        for index, bit in enumerate(pattern):
            if bit == "1":
                x = left + index * module_width
                draw.rectangle((x, 10, x + module_width - 1, 79), fill="black")
        return image
    stream = BytesIO()
    code.write(stream, options={
        "write_text": False, "module_height": 10.0, "quiet_zone": 1.0, "background": "white"})
    stream.seek(0)
    with Image.open(stream) as source:
        return source.convert("RGB").resize((350, 90), Image.Resampling.NEAREST)


def _load_rgb(path: Union[str, Path]) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def generate_single_card(
    front_template_path: CardSource, photo_path: str, output_path: str,
    name: str, student_id: str, class_name: str, class_number: str,
    font_path: Optional[str] = None, use_smart_bg: bool = False,
    cropped_save_path: Optional[str] = None,
    *, chinese_name: str = "", mask_path: str = "", font_eng_path: str = "",
    font_chi_path: str = "", font_id_path: str = "", brightness: float = 1.2,
    portrait_mask: Optional[Image.Image] = None,
) -> Image.Image:
    """Original 649×1033 Colab layout, without generic labels or class text."""
    template = (front_template_path.convert("RGB") if isinstance(front_template_path, Image.Image)
                else _load_rgb(front_template_path))
    mask = None
    try:
        if template.size != (649, 1033):
            raise ValueError("原 Colab 模板須為 649×1033 / School template must be 649×1033")
        if not math.isfinite(brightness) or not 0.1 <= brightness <= 3:
            raise ValueError("Brightness must be between 0.1 and 3")
        if portrait_mask is None:
            if not isinstance(front_template_path, Image.Image):
                assets = _school_assets(str(front_template_path), mask_path, font_eng_path or font_path or "",
                                        font_chi_path, font_id_path)
                mask_path = assets["mask_path"]
                font_eng_path, font_chi_path, font_id_path = (assets[key] for key in (
                    "font_eng_path", "font_chi_path", "font_id_path"))
            mask = _load_mask(mask_path, template.size)
        else:
            mask = portrait_mask.copy()
        with crop_for_eclass(photo_path) as cropped:
            if cropped_save_path:
                Path(cropped_save_path).parent.mkdir(parents=True, exist_ok=True)
                cropped.save(cropped_save_path, quality=95)
        with process_card_face(photo_path, brightness=brightness) as face:
            portrait = remove_green_screen_to_white(face) if use_smart_bg else face.copy()
            try:
                with Image.new("RGB", template.size, "white") as canvas:
                    canvas.paste(portrait, (155, 347))
                    composed = Image.composite(canvas, template, mask)
                template.close()
                template = composed
            finally:
                portrait.close()
        draw = ImageDraw.Draw(template)
        chinese = clean_str(chinese_name)
        if chinese.casefold() in {"", "/", "／", "nan"}:
            chinese = ""
        english = clean_str(name)
        if chinese:
            if english:
                _draw_fitted(draw, (324, 742), english, font_eng_path or font_path or None, 46, 609)
            _draw_fitted(draw, (324, 812), chinese, font_chi_path or None, 65, 609)
        elif english:
            _draw_fitted(draw, (324, 768), english, font_eng_path or font_path or None, 46, 609)
        with _barcode_image(student_id) as barcode:
            template.paste(barcode, (149, 863))
        _draw_fitted(draw, (324, 960), student_id, font_id_path or None, 42, 609, anchor="mt")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        template.save(output_path, format="PNG")
    except Exception:
        template.close()
        raise
    finally:
        if mask is not None:
            mask.close()
    return template


def create_3x4_review_pdf(front_cards: Iterable[CardSource], output_pdf_path: str) -> None:
    """Keep one A4 page in RAM; replace the final PDF only after export succeeds."""
    output = Path(output_pdf_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    cards = iter(front_cards)
    page_w, page_h = 2480, 3508
    cell_w, cell_h = page_w / 3, page_h / 4
    page_count = 0
    with TemporaryDirectory(prefix=".review-", dir=output.parent) as temporary:
        working = Path(temporary) / "review.pdf"
        while True:
            batch = list(islice(cards, 12))
            if not batch:
                break
            with Image.new("RGB", (page_w, page_h), "white") as page:
                for index, source in enumerate(batch):
                    card = source.convert("RGB") if isinstance(source, Image.Image) else _load_rgb(source)
                    try:
                        with ImageOps.contain(card, (int(cell_w * 0.95), int(cell_h * 0.95)),
                                              method=Image.Resampling.LANCZOS) as resized:
                            x = int((index % 3) * cell_w + (cell_w - resized.width) / 2)
                            y = int((index // 3) * cell_h + (cell_h - resized.height) / 2)
                            page.paste(resized, (x, y))
                    finally:
                        card.close()
                page.save(working, "PDF", resolution=300.0, append=page_count > 0)
            page_count += 1
        if not page_count:
            raise ValueError("沒有卡片可供排版 / No cards to export")
        working.replace(output)


def batch_generate_cards(
    excel_path: str, photos_dir: str, front_template: str, output_dir: str,
    export_3x4_pdf: bool = True, use_smart_bg: bool = False,
    progress_callback: ProgressCallback = None,
    mask_path: str = "", font_eng_path: str = "", font_chi_path: str = "",
    font_id_path: str = "", brightness: float = 1.2,
    back_path: str = "", export_student_pdfs: bool = False,
    pdf_width_mm: float = 54.0, pdf_height_mm: float = 85.6,
) -> ProcessStats:
    students = read_students(excel_path)
    _, destination, files = _photo_source(photos_dir, output_dir)
    template = _load_rgb(front_template)
    mask = None
    try:
        if template.size != (649, 1033):
            raise ValueError("原 Colab 模板須為 649×1033 / School template must be 649×1033")
        if not math.isfinite(brightness) or not 0.1 <= brightness <= 3:
            raise ValueError("Brightness must be between 0.1 and 3")
        assets = _school_assets(front_template, mask_path, font_eng_path, font_chi_path, font_id_path)
        mask = _load_mask(assets["mask_path"], template.size)
        if export_student_pdfs:
            back_path = back_path or str(Path(front_template).expanduser().resolve().parent / "back2026.png")
            _validate_pdf_back(back_path, pdf_width_mm, pdf_height_mm)
        get_detector()
        index = defaultdict(list)
        for photo in files:
            index[photo.stem.casefold()].append(photo)
        counts = Counter(row["student_id"].casefold() for row in students)
        output = _new_output(destination, "cards")
        stats = ProcessStats(total=len(students), output_dir=str(output))
        cards_dir, crops_dir = output / "single_cards", output / "cropped_photos"
        cards_dir.mkdir()
        crops_dir.mkdir()
        generated = []
        used_names = set()
        for current, row in enumerate(students, 1):
            sid, name = row["student_id"], row["name"]
            card_path = crop_path = None
            try:
                if row["issues"]:
                    raise ValueError("; ".join(row["issues"]))
                if not sid or not name:
                    raise ValueError("學號或姓名為空 / Missing student ID or name")
                if counts[sid.casefold()] > 1:
                    raise ValueError(f"重複學號 / Duplicate student ID: {sid}")
                matches = index.get(sid.casefold(), [])
                if not matches:
                    raise ValueError(f"找不到相片 / Photo not found: {sid}")
                if len(matches) > 1:
                    raise ValueError(f"同學號有多張相片 / Multiple photos for ID: {sid}")
                stem = "_".join(_safe_component(row[key]) for key in ("student_id", "class_name", "name"))
                if stem.casefold() in used_names:
                    stem += f"_row{row['row']}"
                used_names.add(stem.casefold())
                card_path, crop_path = cards_dir / f"{stem}.png", crops_dir / f"{stem}_cropped.jpg"
                card = generate_single_card(template, str(matches[0]), str(card_path), row["english_name"], sid,
                                            row["class_name"], row["class_number"],
                                            use_smart_bg=use_smart_bg, cropped_save_path=str(crop_path),
                                            chinese_name=row["chinese_name"], portrait_mask=mask,
                                            brightness=brightness, **{k: v for k, v in assets.items() if k != "mask_path"})
                card.close()
                generated.append(card_path)
                stats.success += 1
            except Exception as exc:
                for partial in (card_path, crop_path):
                    if partial is not None:
                        partial.unlink(missing_ok=True)
                stats.failed += 1
                stats.errors.append(f"Row {row['row']} — {sid} ({name}): {exc}")
            if progress_callback:
                progress_callback(current, stats.total, f"{sid} - {name}")
        if export_3x4_pdf and generated:
            if progress_callback:
                progress_callback(stats.total, stats.total, "正在排版 / Creating 3×4 PDF")
            try:
                pdf = output / "student_cards_review_3x4.pdf"
                create_3x4_review_pdf(generated, str(pdf))
                stats.review_pdf = str(pdf)
            except Exception as exc:
                stats.errors.append(f"3×4 檢閱 PDF 生成失敗 / Review PDF export failed: {exc}")
        if export_student_pdfs and generated:
            try:
                _export_student_pdfs(generated, back_path, output, stats, pdf_width_mm, pdf_height_mm,
                                     progress_callback)
            except Exception as exc:
                stats.pdf_failed = len(generated) - stats.pdf_success
                stats.errors.append(f"正背面 PDF 匯出失敗 / Front-back PDF export failed: {exc}")
        return stats
    finally:
        if mask is not None:
            mask.close()
        template.close()


def _validate_pdf_back(back_path, width_mm, height_mm):
    validate_page_size(width_mm, height_mm)
    if not str(back_path).strip():
        raise ValueError("請指定背面圖片 / Select a back image")
    with pdf_image(back_path):
        pass


def _export_student_pdfs(fronts, back_path, output, stats, width_mm, height_mm, progress_callback):
    """Card counts stay separate from export counts; never claim a missing PDF."""
    fronts = sorted(fronts, key=lambda path: (path.name.casefold(), path.name))
    pdf_dir = output / "individual_pdfs"
    pdf_dir.mkdir()
    successful = []
    stems = Counter(path.stem.casefold() for path in fronts)
    with pdf_image(back_path) as back:
        for current, front in enumerate(fronts, 1):
            target = pdf_dir / f"{front.stem}.pdf"
            try:
                if stems[front.stem.casefold()] > 1:
                    raise ValueError("重複正面檔名 / Duplicate front filename stem")
                create_student_pdf(front, back, target, width_mm, height_mm)
                successful.append(target)
                stats.pdf_success += 1
            except Exception as exc:
                stats.pdf_failed += 1
                stats.errors.append(f"PDF {front.name}: {exc}")
            if progress_callback:
                progress_callback(current, len(fronts), f"正背面 PDF / Front-back PDF: {front.name}")
    if successful:
        stats.individual_pdf_dir = str(pdf_dir)
        try:
            if progress_callback:
                progress_callback(len(fronts), len(fronts), "合併總 PDF / Merging all student PDFs")
            combined = output / "All_Students_Combined.pdf"
            merge_student_pdfs(successful, combined)
            stats.combined_pdf = str(combined)
        except Exception as exc:
            stats.errors.append(f"總 PDF 合併失敗 / Combined PDF export failed: {exc}")


def batch_generate_pdfs(fronts_dir: str, back_path: str, output_dir: str,
                        pdf_width_mm: float = 54.0, pdf_height_mm: float = 85.6,
                        progress_callback: ProgressCallback = None) -> ProcessStats:
    """PDF-only workflow: no Excel, detector, template, or source photo required."""
    _, destination, files = _photo_source(fronts_dir, output_dir)
    back = Path(back_path).expanduser().resolve() if str(back_path).strip() else None
    files = [path for path in files if path.resolve() != back and not path.name.startswith("._")]
    if not files:
        raise ValueError("沒有正面圖片 / No front card images found")
    _validate_pdf_back(back_path, pdf_width_mm, pdf_height_mm)
    output = _new_output(destination, "pdf")
    stats = ProcessStats(total=len(files), output_dir=str(output))
    _export_student_pdfs(files, back_path, output, stats, pdf_width_mm, pdf_height_mm, progress_callback)
    stats.success, stats.failed = stats.pdf_success, stats.pdf_failed
    return stats


def batch_crop_eclass_only(photos_dir: str, output_dir: str,
                           progress_callback: ProgressCallback = None) -> ProcessStats:
    _, destination, files = _photo_source(photos_dir, output_dir)
    get_detector()
    output = _new_output(destination, "crop")
    stats = ProcessStats(total=len(files), output_dir=str(output))
    for current, source in enumerate(files, 1):
        target = output / source.name
        try:
            with crop_for_eclass(source) as cropped:
                cropped.save(target, quality=95)
            stats.success += 1
        except Exception as exc:
            target.unlink(missing_ok=True)
            stats.failed += 1
            stats.errors.append(f"{source.name}: {exc}")
        if progress_callback:
            progress_callback(current, stats.total, source.name)
    return stats