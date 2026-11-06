"""End-to-end entry point plus independent artifact-verifier regressions."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def smoke(tmp_path_factory):
    folder = tmp_path_factory.mktemp("current-smoke")
    completed = subprocess.run([sys.executable, str(ROOT / "main.py"), "--smoke-test", str(folder)],
                               cwd=folder, capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return folder


def test_entry_point_and_independent_verification(smoke):
    verify = load_script("verify_release")
    report = verify.verify(smoke)
    assert report["passed"] and len(report["checks"]) == 6
    load_script("build").validate_smoke(smoke / "summary.json")


def test_missing_pdf_cannot_pass_build_validation(smoke, tmp_path):
    summary = json.loads((smoke / "summary.json").read_text())
    summary["cards"]["review_pdf"] = str(tmp_path / "missing.pdf")
    report = tmp_path / "summary.json"
    report.write_text(json.dumps(summary))
    with pytest.raises(RuntimeError, match="review PDF"):
        load_script("build").validate_smoke(report)


def test_reported_export_error_cannot_pass_build_validation(smoke, tmp_path):
    summary = json.loads((smoke / "summary.json").read_text())
    summary["cards"]["errors"] = ["PDF export failed"]
    report = tmp_path / "summary.json"
    report.write_text(json.dumps(summary))
    with pytest.raises(RuntimeError, match="reported errors"):
        load_script("build").validate_smoke(report)