"""Lossless single-card front/back PDFs and ordered merging (not A4 imposition)."""
from __future__ import annotations

from contextlib import contextmanager
import math
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
)


def validate_page_size(width_mm: float, height_mm: float) -> None:
    if any(not math.isfinite(value) or not 10 <= value <= 500 for value in (width_mm, height_mm)):
        raise ValueError("PDF 尺寸必須介於 10–500 mm / PDF dimensions must be between 10 and 500 mm")


@contextmanager
def pdf_image(source):
    """Honor EXIF; flatten transparency onto white, never black."""
    if isinstance(source, Image.Image):
        image = ImageOps.exif_transpose(source).convert("RGBA")
    else:
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original).convert("RGBA")
    try:
        with Image.new("RGBA", image.size, "white") as white:
            flattened = Image.alpha_composite(white, image).convert("RGB")
        try:
            yield flattened
        finally:
            flattened.close()
    finally:
        image.close()


def _add_image_page(writer, image, width_mm, height_mm):
    page_w, page_h = width_mm * 72 / 25.4, height_mm * 72 / 25.4
    page = writer.add_blank_page(width=page_w, height=page_h)
    stream = DecodedStreamObject()
    stream.set_data(image.tobytes())
    encoded = stream.flate_encode()
    encoded.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Image"),
        NameObject("/Width"): NumberObject(image.width),
        NameObject("/Height"): NumberObject(image.height),
        NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
        NameObject("/BitsPerComponent"): NumberObject(8),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/XObject"): DictionaryObject({NameObject("/Card"): writer._add_object(encoded)}),
    })
    scale = min(page_w / image.width, page_h / image.height)
    width, height = image.width * scale, image.height * scale
    x, y = (page_w - width) / 2, (page_h - height) / 2
    content = DecodedStreamObject()
    content.set_data((f"q 1 1 1 rg 0 0 {page_w:.6f} {page_h:.6f} re f Q\n"
                      f"q {width:.6f} 0 0 {height:.6f} {x:.6f} {y:.6f} cm /Card Do Q\n").encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)


def _atomic_write(writer, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".pdf-", dir=destination.parent) as folder:
        temporary = Path(folder) / "result.pdf"
        with temporary.open("wb") as stream:
            writer.write(stream)
        temporary.replace(destination)


def create_student_pdf(front, back, output_path, width_mm=54.0, height_mm=85.6):
    """Exactly two pages, front then back, lossless RGB and aspect-preserving fit."""
    validate_page_size(width_mm, height_mm)
    writer = PdfWriter()
    try:
        for source in (front, back):
            with pdf_image(source) as image:
                _add_image_page(writer, image, width_mm, height_mm)
        _atomic_write(writer, output_path)
    finally:
        writer.close()


def merge_student_pdfs(paths, output_path):
    """Merge the actual successful individual files, in caller-provided order."""
    paths = list(paths)
    if not paths:
        raise ValueError("沒有 PDF 可合併 / No PDFs to merge")
    writer = PdfWriter()
    try:
        for path in paths:
            reader = PdfReader(path)
            if len(reader.pages) != 2:
                raise ValueError(f"每人 PDF 必須為 2 頁 / Expected two pages: {Path(path).name}")
            writer.append(reader, import_outline=False)
        writer.compress_identical_objects()
        _atomic_write(writer, output_path)
    finally:
        writer.close()