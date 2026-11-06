# Third-party software and model notices

Student Card Studio includes or uses the projects below. Original licenses apply to their respective components; the original Notebook and school assets retain their existing ownership. This notice does not grant redistribution rights to proprietary school templates, student photographs, or system fonts.

| Component | License / upstream |
|---|---|
| Python | PSF License — https://www.python.org/psf/license/ |
| PySide6 / Qt for Python | LGPLv3 / GPLv3 / commercial options — https://doc.qt.io/qtforpython-6/licenses.html |
| Qt | LGPLv3 and other component-specific licenses — https://doc.qt.io/qt-6/licensing.html |
| Shiboken6 | LGPLv3 / GPLv3 / commercial options — https://doc.qt.io/qtforpython-6/licenses.html |
| Pillow | HPND / Pillow license — https://github.com/python-pillow/Pillow |
| NumPy | BSD-3-Clause, plus bundled library notices — https://github.com/numpy/numpy |
| OpenCV | Apache-2.0, plus bundled library notices — https://github.com/opencv/opencv |
| OpenCV Python wheels | MIT for packaging code; bundled OpenCV / FFmpeg notices — https://github.com/opencv/opencv-python |
| YuNet ONNX model | MIT, OpenCV Zoo face_detection_yunet — https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet |
| openpyxl | MIT — https://foss.heptapod.net/openpyxl/openpyxl |
| et-xmlfile | MIT — https://foss.heptapod.net/openpyxl/et_xmlfile |
| python-barcode | MIT — https://github.com/WhyNotHugo/python-barcode |
| pypdf | BSD-3-Clause — https://github.com/py-pdf/pypdf |
| zxing-cpp (test/verification only) | Apache-2.0 — https://github.com/zxing-cpp/zxing-cpp |
| PyInstaller runtime | GPLv2+ with bootloader exception — https://pyinstaller.org/en/stable/license.html |

The application uses Qt as separate dynamically linked libraries; it does not modify Qt, PySide6, or Shiboken. Corresponding upstream source and license terms are available at the links above. Users may inspect and replace these third-party libraries under their licenses; when rebuilding, use the supplied source and build scripts. Windows one-file bundles extract their libraries to a temporary directory at startup; for library replacement and debugging, build with `python scripts/build.py --windows-onedir`.

Runtime wheel license files are collected into `third_party_licenses` in the frozen bundle by `scripts/build.py`. pypdf is a runtime dependency for lossless front/back image PDFs and ordered merging. Build/test-only tools (pytest, zxing-cpp, PyInstaller) are listed in `requirements-dev.txt`; zxing-cpp decodes generated Code128 and is not imported by the application.

Fonts are discovered from the current operating system or selected by the user. Windows/macOS proprietary fonts are not copied into the source archive or the application. The demo uses generated drawings and fictional student data.

The blue student-card application icon is an original generated drawing; its editable generation script is `scripts/create_icon.py`.

Source-package-only test fixture `tests/fixtures/astronaut.png` is a public-domain NASA photograph of Eileen Collins; source details are in `tests/fixtures/README.txt`. It is used for offline detector tests and is not included in the frozen application.
