"""
Core logic for StudentCardStudio:
- Card image generation
- Intermediate eClass crop output
- Dual-sided A4 PDF export (2x4)
- Review A4 PDF export (3x4)
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional
import os
import math
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from student_card.face import crop_for_eclass, remove_green_screen_to_white

@dataclass
class ProcessStats:
    total: int = 0
    success: int = 0
    failed: int = 0
    errors: Optional[List[str]] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

def clean_str(val) -> str:
    if pd.isna(val):
        return ""
    val_str = str(val).strip()
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    return val_str

def get_font(font_path: Optional[str], size: int) -> ImageFont.FreeTypeFont:
    if font_path and os.path.isfile(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    fallback_candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "C:\\Windows\\Fonts\\msjh.ttc",
        "C:\\Windows\\Fonts\\simsun.ttc",
    ]
    for candidate in fallback_candidates:
        if os.path.isfile(candidate):
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                continue
    return ImageFont.load_default()

def generate_single_card(
    front_template_path: str,
    photo_path: str,
    output_path: str,
    name: str,
    student_id: str,
    class_name: str,
    class_number: str,
    font_path: Optional[str] = None,
    use_smart_bg: bool = False,
    cropped_save_path: Optional[str] = None,
) -> Image.Image:
    
    cropped_img = crop_for_eclass(photo_path)

    if cropped_save_path:
        os.makedirs(os.path.dirname(cropped_save_path), exist_ok=True)
        cropped_img.save(cropped_save_path, quality=95)

    if use_smart_bg:
        processed_photo = remove_green_screen_to_white(cropped_img)
    else:
        processed_photo = cropped_img.convert("RGB")

    template = Image.open(front_template_path).convert("RGBA")
    tw, th = template.size

    target_photo_w = int(tw * 0.26)
    target_photo_h = int(target_photo_w * 1.333)
    resized_photo = processed_photo.convert("RGBA").resize(
        (target_photo_w, target_photo_h), Image.Resampling.LANCZOS
    )

    photo_x = int(tw * 0.08)
    photo_y = int((th - target_photo_h) / 2)
    template.paste(resized_photo, (photo_x, photo_y), resized_photo)

    draw = ImageDraw.Draw(template)
    font_large = get_font(font_path, int(th * 0.075))
    font_small = get_font(font_path, int(th * 0.055))

    text_x = photo_x + target_photo_w + int(tw * 0.06)
    start_y = photo_y + int(target_photo_h * 0.1)
    line_spacing = int(th * 0.09)

    draw.text((text_x, start_y), f"姓名 Name: {name}", fill="black", font=font_large)
    draw.text((text_x, start_y + line_spacing), f"學號 Student ID: {student_id}", fill="black", font=font_small)
    draw.text((text_x, start_y + line_spacing * 2), f"班別 Class: {class_name} ({class_number})", fill="black", font=font_small)

    card_rgb = template.convert("RGB")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    card_rgb.save(output_path, quality=95)
    return card_rgb

def create_double_sided_pdf(
    front_cards: List[Image.Image],
    back_template_path: Optional[str],
    output_pdf_path: str,
) -> None:
    page_w, page_h = 2480, 3508
    cols, rows = 2, 4
    cards_per_page = cols * rows
    card_w, card_h = 1012, 638
    margin_x = (page_w - (cols * card_w)) // (cols + 1)
    margin_y = (page_h - (rows * card_h)) // (rows + 1)

    back_img = None
    if back_template_path and os.path.exists(back_template_path):
        back_img = Image.open(back_template_path).convert("RGB").resize((card_w, card_h), Image.Resampling.LANCZOS)

    pdf_pages = []
    total_batches = math.ceil(len(front_cards) / cards_per_page)

    for b in range(total_batches):
        batch_cards = front_cards[b * cards_per_page : (b + 1) * cards_per_page]
        
        front_page = Image.new("RGB", (page_w, page_h), "white")
        for idx, card in enumerate(batch_cards):
            r = idx // cols
            c = idx % cols
            x = margin_x + c * (card_w + margin_x)
            y = margin_y + r * (card_h + margin_y)
            resized = card.resize((card_w, card_h), Image.Resampling.LANCZOS)
            front_page.paste(resized, (x, y))
        pdf_pages.append(front_page)

        if back_img:
            back_page = Image.new("RGB", (page_w, page_h), "white")
            for idx in range(len(batch_cards)):
                r = idx // cols
                c = (cols - 1) - (idx % cols)
                x = margin_x + c * (card_w + margin_x)
                y = margin_y + r * (card_h + margin_y)
                back_page.paste(back_img, (x, y))
            pdf_pages.append(back_page)

    if pdf_pages:
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
        pdf_pages[0].save(output_pdf_path, save_all=True, append_images=pdf_pages[1:], resolution=300.0)

def create_3x4_review_pdf(
    front_cards: List[Image.Image],
    output_pdf_path: str,
) -> None:
    page_w, page_h = 2480, 3508
    cols, rows = 3, 4
    cards_per_page = cols * rows
    cell_w = page_w / cols
    cell_h = page_h / rows

    pdf_pages = []
    total_batches = math.ceil(len(front_cards) / cards_per_page)

    for b in range(total_batches):
        batch_cards = front_cards[b * cards_per_page : (b + 1) * cards_per_page]
        page = Image.new("RGB", (page_w, page_h), "white")
        
        for idx, card in enumerate(batch_cards):
            r = idx // cols
            c = idx % cols
            
            orig_w, orig_h = card.size
            scale = min((cell_w * 0.95) / orig_w, (cell_h * 0.95) / orig_h)
            new_w, new_h = int(orig_w * scale), int(orig_h * scale)
            
            resized = card.resize((new_w, new_h), Image.Resampling.LANCZOS)
            x = int(c * cell_w + (cell_w - new_w) / 2)
            y = int(r * cell_h + (cell_h - new_h) / 2)
            page.paste(resized, (x, y))
            
        pdf_pages.append(page)

    if pdf_pages:
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
        pdf_pages[0].save(output_pdf_path, save_all=True, append_images=pdf_pages[1:], resolution=300.0)

def batch_generate_cards(
    excel_path: str,
    photos_dir: str,
    front_template: str,
    back_template: Optional[str],
    output_dir: str,
    export_pdf: bool = True,
    export_3x4_pdf: bool = True,
    use_smart_bg: bool = False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> ProcessStats:
    stats = ProcessStats()
    df = pd.read_excel(excel_path)
    stats.total = len(df)

    cropped_dir = os.path.join(output_dir, "cropped_photos")
    cards_dir = os.path.join(output_dir, "single_cards")
    os.makedirs(cropped_dir, exist_ok=True)
    os.makedirs(cards_dir, exist_ok=True)

    generated_front_cards = []

    for idx, row in df.iterrows():
        student_id = clean_str(row.get("StudentID") or row.get("學號") or row.get("ID"))
        name = clean_str(row.get("Name") or row.get("姓名"))
        class_name = clean_str(row.get("Class") or row.get("班別"))
        class_num = clean_str(row.get("ClassNumber") or row.get("學號/班號") or row.get("ClassNo"))

        if progress_callback:
            progress_callback(idx + 1, stats.total, f"{student_id} - {name}")

        photo_candidates = [
            os.path.join(photos_dir, f"{student_id}.jpg"),
            os.path.join(photos_dir, f"{student_id}.png"),
            os.path.join(photos_dir, f"{student_id}.jpeg"),
        ]
        matched_photo = next((p for p in photo_candidates if os.path.exists(p)), None)

        if not matched_photo:
            stats.failed += 1
            stats.errors.append(f"找不到相片: {student_id} ({name})")
            continue

        output_card_path = os.path.join(cards_dir, f"{student_id}_{class_name}_{name}.jpg")
        cropped_photo_path = os.path.join(cropped_dir, f"{student_id}_{name}_cropped.jpg")

        try:
            card_img = generate_single_card(
                front_template_path=front_template,
                photo_path=matched_photo,
                output_path=output_card_path,
                name=name,
                student_id=student_id,
                class_name=class_name,
                class_number=class_num,
                use_smart_bg=use_smart_bg,
                cropped_save_path=cropped_photo_path,
            )
            generated_front_cards.append(card_img)
            stats.success += 1
        except Exception as e:
            stats.failed += 1
            stats.errors.append(f"{student_id} ({name}): {str(e)}")

    if export_pdf and generated_front_cards:
        try:
            pdf_path = os.path.join(output_dir, "student_cards_print_A4.pdf")
            create_double_sided_pdf(generated_front_cards, back_template, pdf_path)
        except Exception as e:
            stats.errors.append(f"雙面 PDF 生成失敗: {str(e)}")

    if export_3x4_pdf and generated_front_cards:
        try:
            pdf_3x4_path = os.path.join(output_dir, "student_cards_review_3x4.pdf")
            create_3x4_review_pdf(generated_front_cards, pdf_3x4_path)
        except Exception as e:
            stats.errors.append(f"3x4 檢閱 PDF 生成失敗: {str(e)}")

    return stats

def batch_crop_eclass_only(
    photos_dir: str,
    output_dir: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> ProcessStats:
    stats = ProcessStats()
    valid_extensions = {".jpg", ".jpeg", ".png"}
    files = [f for f in os.listdir(photos_dir) if os.path.splitext(f)[1].lower() in valid_extensions]
    stats.total = len(files)
    os.makedirs(output_dir, exist_ok=True)

    for idx, fname in enumerate(files):
        src_path = os.path.join(photos_dir, fname)
        out_path = os.path.join(output_dir, fname)
        if progress_callback:
            progress_callback(idx + 1, stats.total, fname)
        try:
            cropped = crop_for_eclass(src_path)
            cropped.save(out_path, quality=95)
            stats.success += 1
        except Exception as e:
            stats.failed += 1
            stats.errors.append(f"{fname}: {str(e)}")
    return stats