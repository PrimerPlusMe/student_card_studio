# Internal interface contract

All paths use pathlib.Path or strings accepted by Path. UI uses JSON serializable dict config.
Core module: student_card/core.py. No Qt imports.

Functions:
- default_config() -> dict (all file paths empty strings; keys below)
- inspect_inputs(config: dict, mode: str = 'cards') -> dict
  Returns {'ok': bool, 'errors': list[str], 'warnings': list[str], 'students': list[dict], 'photo_count': int}.
  students entries: {'student_id': str, 'english_name': str, 'chinese_name': str, 'photo': str, 'issues': list[str]}.
- preview_card(config, student_id: str | None = None) -> PIL.Image.Image
- run_job(config, mode='cards', progress=None, cancelled=None) -> dict
  progress(percent:int, message:str), cancelled() -> bool. mode: cards / pdf / crop.
  Return {'output_dir': str, 'success': int, 'failed': int, 'skipped': int, 'review': int, 'cancelled': bool}.
  Do not overwrite input files. Every job creates unique output subdirectory; UTF-8-SIG CSV and JSON manifest, ZIP.
- create_demo(destination: Path) -> dict: generates synthetic photos, xlsx, template/mask/back. Returns ready config.

Config keys:
excel_path, photo_path (folder/zip), template_path, mask_path, back_path,
font_eng_path, font_chi_path, font_id_path, output_dir, pdf_input_dir (all str).
brightness=1.15, face_ratio=0.32, photo_offset_y=0, center_x=324,
photo_x=155, photo_y=347, face_radius=170, eng_only_y=768, eng_dual_y=742,
chi_dual_y=812, eng_font_size=46, chi_font_size=65, id_font_size=42,
barcode_width=350, barcode_height=90, barcode_bottom_y=953, id_text_top_y=960,
reference_width=648, reference_height=1050 (template coordinates scaled to actual size),
pdf_width_mm=54.0, pdf_height_mm=85.6, make_pdf=True, make_zip=True,
detector='opencv' phase 1 Haar / phase 2 YuNet, model_path='',
column_id='學號', column_eng='Name', column_chi='姓名'.

Face interface student_card/face.py:
class FaceDetector: __init__(model_path: str = '', backend: str = 'opencv');
detect(image: PIL.Image.Image) -> dict | None containing box=(x,y,w,h), nose=(x,y), count=int.
Phase 1 uses Haar; phase 2 updates same interface to YuNet. Core uses returned count to mark review, fallback marks review.

Stage 1 must pass end-to-end tests before Phase 2 model changes. Demo photos are drawings, not real student data.
