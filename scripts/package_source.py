"""Create a source archive without virtualenvs, credentials, or user input data."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package(destination: Path, notebook: Path | None = None):
    if notebook is not None:
        # Notebook outputs may contain real names: only preserve executable source.
        document = json.loads(notebook.read_text(encoding="utf-8-sig"))
        for cell in document.get("cells", []):
            if cell.get("cell_type") == "code":
                cell["outputs"] = []
                cell["execution_count"] = None
            cell["metadata"] = {}
        document["metadata"] = {"language_info": {"name": "python"}}
        target = ROOT / "docs" / "original" / notebook.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8")
    files = []
    for name in ("main.py", "README.md", "requirements.txt", "requirements-dev.txt", "THIRD_PARTY_NOTICES.md", ".gitignore", "pytest.ini"):
        path = ROOT / name
        if path.is_file():
            files.append(path)
    for name in ("student_card", "assets", "tests", "scripts", "docs", ".github"):
        files.extend(path for path in (ROOT / name).rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"})
    # Historical reports belong to older APIs; do not ship them as current evidence.
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(set(files), key=lambda item: str(item.relative_to(ROOT))):
            archive.write(file, Path("StudentCardStudio") / file.relative_to(ROOT))
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Source archive verification failed")
        required = {"StudentCardStudio/main.py", "StudentCardStudio/student_card/core.py",
                    "StudentCardStudio/assets/face_detection_yunet_2023mar.onnx",
                    "StudentCardStudio/.github/workflows/build.yml", "StudentCardStudio/tests/fixtures/astronaut.png"}
        if not required.issubset(set(archive.namelist())):
            raise RuntimeError("Source archive is incomplete")
    with destination.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        digest = digest.hexdigest()
    destination.with_suffix(".zip.sha256").write_text(f"{digest}  {destination.name}\n", encoding="utf-8")
    print(json.dumps({"archive": str(destination), "files": len(files), "bytes": destination.stat().st_size, "sha256": digest}, ensure_ascii=False))
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "release" / "StudentCardStudio-source.zip")
    parser.add_argument("--notebook", type=Path)
    options = parser.parse_args()
    package(options.output, options.notebook)
