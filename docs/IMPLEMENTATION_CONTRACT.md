# Current interface contract

Core has no Qt dependency. Python 3.9+ syntax is supported with postponed annotations.

## Core

- `read_students(excel_path) -> list[dict]`: first `.xlsx` worksheet; ID/name are required headers. Records contain `row`, `student_id`, `name` (filename fallback), separate `english_name`/`chinese_name`, `class_name`, `class_number`, `issues`. Text IDs and pure-zero numeric formats are preserved. Formula/error cells are reported as row issues, never silently evaluated.
- `batch_generate_cards(..., brightness=1.2, back_path='', export_student_pdfs=False, pdf_width_mm=54.0, pdf_height_mm=85.6) -> ProcessStats`. Original 649×1033 template and same-size mask required. Resources can be found by original names beside template; no school assets are bundled. PNG output. Enabled student-PDF export validates the back before any job and then exports successful fronts; blank back searches template sibling `back2026.png`.
- `batch_generate_pdfs(fronts_dir, back_path, output_dir, pdf_width_mm=54.0, pdf_height_mm=85.6, progress_callback=None) -> ProcessStats`: PDF-only, no detector or Excel. Unique `pdf_…` job. Scans first-level images, excludes selected back/AppleDouble files, rejects duplicate stems per record. Source/output overlap forbidden.
- `batch_crop_eclass_only(photos_dir, output_dir, progress_callback=None) -> ProcessStats`.
- `generate_single_card(..., *, chinese_name='', mask_path='', font_eng_path='', font_chi_path='', font_id_path='', brightness=1.2, portrait_mask=None) -> PIL.Image.Image`; caller owns returned image. Masked portrait at (155,347), centered dual/single names, 350×90 Code128 at (149,863), ID top (324,960). Class fields are retained for compatibility/filenames but not drawn. Too-long names shrink; longer barcodes use integral modules. No barcode temporary file on disk.
- `create_3x4_review_pdf(front_cards, output_pdf_path) -> None`: iterable of PIL images or file paths, row-major 3 columns × 4 rows, single-sided A4 at 300 DPI. Loads one page at a time and replaces destination on success. Empty input raises ValueError.

`ProcessStats`: `total`, `success`, `failed`, `errors`, `output_dir`, `review_pdf`, `individual_pdf_dir`, `combined_pdf`, `pdf_success`, `pdf_failed`. `total == success + failed` for completed batches. Card-task PDF errors do not change card-success counts. PDF-only success/failed mirror pdf_success/pdf_failed. Output paths stay empty unless successful files exist; merge failure preserves individual PDFs and leaves combined_pdf empty.

`student_card.pdf.create_student_pdf(front, back, output_path, width_mm=54.0, height_mm=85.6)` writes exactly two pages with lossless RGB images, transparency flattened on white and aspect-preserving centered fit. `merge_student_pdfs(paths, output_path)` merges actual 2-page individual files in input order. Core sorts by `(filename.casefold(), filename)` and only merges successful individual PDFs. Both use atomic replacement and private temporary directories. Fixed page dimensions must be finite, 10–500 mm. This is not A4 multi-card imposition.

Progress callback: `(current: int, total: int, description: str)`. Called after each attempted record and before PDF export. Reaching the last record does not mean PDF export has finished.

Each batch creates a unique child of output_dir. Invalid overall inputs raise before creating a job. Per-record errors continue. Source photos are read from the first directory level, not ZIP or recursion. Output cannot be within the photo source.

## Face

- `get_detector()`: lazy cached YuNet model; synchronized construction.
- `detect_face(bgr_array) -> (x, y, width, height) | None`: largest face, coordinates mapped back to source, synchronized inference, max inference edge 1200 px.
- `detect_face_landmarks(bgr_array) -> {'box': tuple, 'nose': tuple, 'count': int} | None`: YuNet nose indices 8/9 mapped to original coordinates. Not a claim of MTCNN equivalence.
- `process_card_face(image, brightness=1.2, radius=170, face_ratio=0.32)`: original Colab resize/crop formula, nose anchor, top offset -10px; white padding prevents the old portrait leaking through.
- `crop_for_eclass(path_or_pil) -> PIL.Image.Image`: applies EXIF orientation, exact 10:13 maximal-area crop, face anchor or 40%-height fallback. Very small images become 10×13 pixels. Integral ratio differs from Colab floor by at most 12px.
- `remove_green_screen_to_white(image) -> PIL.Image.Image`: green mask or GrabCut; caller opts in.

## GUI / demo

`StudentCardMainWindow(persist=True, settings=None)` has card/crop/PDF-only tabs. `WorkerThread` captures result/error; GUI restores all three actions on QThread.finished. One job at a time; closing ignored until completion. Card tab scrolls on small displays.

Stable QSettings INI user-scope `StudentCardStudio/StudentCardStudio` records all PATH_FIELDS, CHECK_FIELDS, NUMBER_FIELDS, language and tab. Debounced autosave plus explicit save before jobs/close. Offline paths remain stored. `persist=False` disables all settings IO; tests inject temporary QSettings. Smoke uses an isolated INI in its destination, verifies restoration, and never touches user settings.

`student_card.demo.create_demo(destination) -> dict` returns ready card keyword arguments and writes fictional `back2026.png`. `main.py --smoke-test destination` exercises card+PDF, PDF-only, and crop; summary contains all three. Build and independent verification require individual and combined PDFs, correct lossless front/back order, physical dimensions, Code128, 3×4 review and exact crop ratio.

No A4 double-sided imposition API exists. Legacy `run_job`, `MainWindow`, `FaceDetector` and other phase-one interfaces are not current APIs.