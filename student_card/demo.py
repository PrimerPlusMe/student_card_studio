"""Generate small, synthetic fixtures without bundling personal data or fonts."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from openpyxl import Workbook


def _font(size: int) -> ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size=size)


def _portrait(path: Path, accent: str, seed: int) -> None:
    image = Image.new("RGB", (600, 850), "#e9eef4")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((28, 28, 572, 822), radius=32, fill="#f7f9fc")
    draw.ellipse((125, 510, 475, 1040), fill=accent)
    draw.rectangle((255, 444, 345, 567), fill="#e2af8e")
    draw.ellipse((178, 163, 422, 487), fill="#edbf9d")
    draw.pieslice((163, 113, 436, 360), 175, 365, fill="#343844")
    draw.ellipse((227, 301, 245, 315), fill="#353945")
    draw.ellipse((355, 301, 373, 315), fill="#353945")
    draw.line((300, 321, 288, 369, 308, 369), fill="#ae7557", width=5)
    draw.arc((256, 365, 343, 419), 10, 170, fill="#9a5d4b", width=6)
    draw.text((300, 766), f"SYNTHETIC SAMPLE {seed}", font=_font(22), anchor="mm", fill="#617086")
    image.save(path, quality=95)


def create_demo(destination: str | Path) -> dict:
    """Write demonstration assets and return a complete application config.

    All students and portraits are invented. System fonts are referenced, never
    copied into a redistributable asset directory.
    """
    from .core import default_config

    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    photos = root / "photos"
    photos.mkdir(exist_ok=True)
    template = Image.new("RGB", (648, 1050), "white")
    draw = ImageDraw.Draw(template)
    draw.rectangle((0, 0, 648, 216), fill="#173f63")
    draw.text((324, 76), "DEMO SCHOOL", anchor="mm", font=_font(47), fill="white")
    draw.text((324, 146), "STUDENT CARD", anchor="mm", font=_font(29), fill="#cfe5ef")
    draw.text((324, 265), "SYNTHETIC DEMONSTRATION", anchor="mm", font=_font(22), fill="#617086")
    draw.ellipse((150, 342, 500, 692), fill="#e7edf5", outline="#c6d4e3", width=3)
    draw.rectangle((0, 1024, 648, 1050), fill="#173f63")
    template.save(root / "template.png")
    mask = Image.new("L", template.size, 0)
    ImageDraw.Draw(mask).ellipse((155, 347, 494, 686), fill=255)
    mask.save(root / "mask.png")
    back = Image.new("RGB", template.size, "#173f63")
    draw = ImageDraw.Draw(back)
    draw.text((324, 220), "DEMO SCHOOL", anchor="mm", font=_font(43), fill="white")
    draw.text((324, 310), "STUDENT CARD / BACK", anchor="mm", font=_font(27), fill="#cfe5ef")
    draw.multiline_text((65, 460), "Demonstration only.\nAll student records are fictional.\n\nIf found, please return to\nthe school office.", spacing=23, font=_font(24), fill="white")
    back.save(root / "back.png")
    rows = (
        ("00001", "ALEX CHAN", "陳同學", "#3987ad"),
        ("00002", "A VERY LONG ENGLISH STUDENT NAME FOR LAYOUT CHECK", "/", "#497a61"),
        ("00003", "JAMIE LEE", "李同學", "#97679d"),
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Students"
    sheet.append(["學號", "Name", "姓名"])
    for index, (student_id, english, chinese, accent) in enumerate(rows, 1):
        sheet.append([student_id, english, chinese])
        sheet.cell(index + 1, 1).number_format = "@"
        _portrait(photos / f"{student_id}.jpg", accent, index)
    sheet.column_dimensions["A"].width = 18
    sheet.column_dimensions["B"].width = 65
    sheet.column_dimensions["C"].width = 20
    workbook.save(root / "students.xlsx")
    (root / "演示资料说明.txt").write_text(
        "本目录的学生记录与人像均为虚构演示资料，不含真实学生信息。\n"
        "演示人像为程序绘制，可能不能被人脸检测模型识别；此时会标记为需要复核。\n"
        "实际使用请替换为自己的底图、遮罩、背面、名单和按学号命名的照片。\n"
        "学号请在 Excel 中使用文本，或使用明确的前导零数字格式。\n"
        "字体引用操作系统已有字体；本目录没有复制系统字体文件。\n",
        encoding="utf-8",
    )
    config = default_config()
    config.update(
        excel_path=str(root / "students.xlsx"),
        photo_path=str(photos),
        template_path=str(root / "template.png"),
        mask_path=str(root / "mask.png"),
        back_path=str(root / "back.png"),
        output_dir=str(root / "output"),
        reference_width=648,
        reference_height=1050,
    )
    return config
