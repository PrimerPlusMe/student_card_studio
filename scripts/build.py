"""Build native Windows/macOS distributions; never cross-compiles.

Run with the project's Python environment: python scripts/build.py
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import distribution
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = "StudentCardStudio"


def collect_license_files(destination: Path) -> None:
    """Copy licenses shipped by runtime wheels; do not copy user data or fonts."""
    destination.mkdir(parents=True, exist_ok=True)
    distributions = [
        "PySide6-Essentials", "shiboken6", "Pillow", "numpy", "opencv-python-headless",
        "openpyxl", "et-xmlfile", "python-barcode", "img2pdf", "pikepdf", "lxml",
        "pypdf", "packaging", "Deprecated", "wrapt", "PyInstaller",
    ]
    versions = {}
    for name in distributions:
        package = distribution(name)
        versions[name] = package.version
        target = destination / name
        target.mkdir(exist_ok=True)
        for member in package.files or []:
            filename = Path(str(member)).name.lower()
            if not filename.startswith(("license", "copying", "copyright", "notice")):
                continue
            source = Path(package.locate_file(member))
            if not source.is_file() or source.suffix in {".py", ".pyc", ".xml"}:
                continue
            # Keep names unique when a wheel ships several nested license files.
            relative = str(member).replace("\\", "/").replace("../", "").replace("/", "__")
            shutil.copyfile(source, target / relative)
        metadata = package.read_text("METADATA")
        if metadata:
            (target / "PACKAGE_METADATA.txt").write_text(metadata, encoding="utf-8")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copyfile(python_license, destination / "PYTHON_LICENSE.txt")
    (destination / "versions.json").write_text(json.dumps(versions, indent=2), encoding="utf-8")


def run(command: list[str], *, timeout: int = 1800, env: dict | None = None) -> None:
    # Signing secrets are passed through env/keychain rather than logged.
    effective = dict(os.environ if env is None else env)
    for key in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        effective.pop(key, None)
    if platform.system() == "Windows":
        # DLL discovery follows PATH. Third-party applications can put incompatible
        # UCRT/API-set DLLs there, which must never enter this distribution.
        windows = Path(effective.get("WINDIR", "C:/Windows"))
        effective["PATH"] = os.pathsep.join(str(path) for path in (
            Path(sys.executable).parent, Path(sys.base_prefix),
            Path(sys.base_prefix) / "DLLs", windows / "System32", windows,
        ))
    effective["PYTHONUTF8"] = "1"
    subprocess.run(command, cwd=ROOT, env=effective, check=True, timeout=timeout)


def smoke(executable: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    summary_file = destination / "summary.json"
    summary_file.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    run([str(executable), "--smoke-test", str(destination)], timeout=300, env=environment)
    validate_smoke(summary_file)


def validate_smoke(summary_file: Path) -> None:
    if not summary_file.is_file():
        raise RuntimeError(f"Smoke check did not create {summary_file}")
    report = json.loads(summary_file.read_text(encoding="utf-8"))
    if report.get("passed") is not True:
        raise RuntimeError(f"Smoke check did not pass: {summary_file}")
    for operation in ("cards", "pdf", "crop"):
        result = report.get(operation, {})
        if result.get("failed") != 0 or result.get("success", 0) < 1 or result.get("cancelled"):
            raise RuntimeError(f"Smoke operation {operation} failed: {summary_file}")


def build(*, skip_tests: bool = False, windows_onedir: bool = False) -> Path:
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        raise RuntimeError("Build on Windows for .exe or on macOS for .app; no cross-compilation.")
    model = ROOT / "assets" / "face_detection_yunet_2023mar.onnx"
    if not model.is_file() or model.stat().st_size < 100_000:
        raise RuntimeError("Bundled YuNet ONNX model is missing or incomplete.")
    verification = ROOT / "verification"
    verification.mkdir(exist_ok=True)
    if not skip_tests:
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        run([sys.executable, "-m", "pytest", "-q", "--junitxml", str(verification / "pytest-junit.xml")],
            timeout=600, env=environment)

    dist = ROOT / "dist"
    work = ROOT / "build"
    release = ROOT / "release"
    for directory in (dist, work, release):
        directory.mkdir(exist_ok=True)
    license_directory = work / "third_party_licenses"
    collect_license_files(license_directory)
    source_smoke = ROOT / "verification" / "source_smoke"
    source_smoke.mkdir(parents=True, exist_ok=True)
    (source_smoke / "summary.json").unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    run([sys.executable, str(ROOT / "main.py"), "--smoke-test", str(source_smoke)],
        timeout=300, env=environment)
    validate_smoke(source_smoke / "summary.json")

    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", NAME, "--distpath", str(dist), "--workpath", str(work),
        "--specpath", str(work), "--paths", str(ROOT),
        "--add-data", f"{ROOT / 'assets'}{os.pathsep}assets",
        "--add-data", f"{license_directory}{os.pathsep}third_party_licenses",
        "--add-data", f"{ROOT / 'THIRD_PARTY_NOTICES.md'}{os.pathsep}.",
        "--collect-data", "cv2",
    ]
    # Keep the Qt desktop widget runtime; deliberately omit unrelated engines.
    excluded = [
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQml", "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtNetworkAuth",
        "PySide6.QtGraphs", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "tkinter", "matplotlib", "pandas", "tensorflow", "torch", "IPython", "pytest",
    ]
    for module in excluded:
        command.extend(["--exclude-module", module])
    if system == "Windows":
        command.append("--onedir" if windows_onedir else "--onefile")
        icon = ROOT / "assets" / "app.ico"
        if icon.exists():
            command.extend(["--icon", str(icon)])
    else:
        command.extend(["--onedir", "--osx-bundle-identifier", "org.studentcardstudio.desktop"])
        # Optional Developer ID identity is already installed in the keychain by CI.
        identity = os.environ.get("MACOS_SIGNING_IDENTITY", "").strip()
        if identity:
            command.extend(["--codesign-identity", identity])
        icon = ROOT / "assets" / "app.icns"
        if icon.exists():
            command.extend(["--icon", str(icon)])
    command.append(str(ROOT / "main.py"))
    run(command)

    architecture = platform.machine().lower()
    if architecture in {"amd64", "x86_64"}:
        architecture = "x64"
    elif architecture in {"aarch64", "arm64"}:
        architecture = "arm64"
    target = f"{'macos' if system == 'Darwin' else 'windows'}-{architecture}"
    frozen_smoke = ROOT / "verification" / f"frozen_{target}"
    executable = (dist / f"{NAME}.app" / "Contents" / "MacOS" / NAME if system == "Darwin"
                  else dist / NAME / f"{NAME}.exe" if windows_onedir
                  else dist / f"{NAME}.exe")
    smoke(executable, frozen_smoke)

    archive = release / f"{NAME}-{target}.zip"
    if system == "Darwin":
        # GitHub upload-artifact does not itself preserve executable bits/symlinks.
        # ditto's archive preserves .app bundle layout, permissions and resource forks.
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
             str(dist / f"{NAME}.app"), str(archive)])
    else:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            if windows_onedir:
                for path in sorted((dist / NAME).rglob("*")):
                    if path.is_file():
                        bundle.write(path, path.relative_to(dist))
            else:
                bundle.write(executable, executable.name)
            for relative in ("README.md", "THIRD_PARTY_NOTICES.md", "docs/使用说明.md",
                             "docs/阶段验收记录.md"):
                path = ROOT / relative
                if path.exists():
                    bundle.write(path, relative)
    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    metadata = {
        "artifact": archive.name, "sha256": digest, "platform": platform.platform(),
        "architecture": architecture, "python": platform.python_version(),
        "source_smoke": str(source_smoke.relative_to(ROOT)),
        "frozen_smoke": str(frozen_smoke.relative_to(ROOT)),
        "developer_id_signed": bool(os.environ.get("MACOS_SIGNING_IDENTITY")) if system == "Darwin" else False,
        "notarized": False,
    }
    (release / f"build-{target}.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Built and smoke-tested: {archive}")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true", help="Use only after current source pytest already passed.")
    parser.add_argument("--windows-onedir", action="store_true", help="Windows development build as a folder.")
    options = parser.parse_args()
    build(skip_tests=options.skip_tests, windows_onedir=options.windows_onedir)
