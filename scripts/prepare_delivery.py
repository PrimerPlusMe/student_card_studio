"""Assemble the reviewed Windows application and source into a delivery folder."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
import shutil
import zipfile

from package_source import package

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        return digest.hexdigest()


def deliver(destination: Path, notebook: Path | None = None):
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    report = json.loads((ROOT / "validation/windows-exe/release-verification.json").read_text(encoding="utf-8"))
    if report.get("passed") is not True:
        raise RuntimeError("The executable has not passed independent release validation")
    executable = ROOT / "dist/StudentCardStudio.exe"
    if report.get("exe_sha256") != sha256(executable):
        raise RuntimeError("Run verify_release.py --executable on this exact executable before delivery")
    exe = destination / executable.name
    shutil.copy2(executable, exe)
    for source, name in (
        (ROOT / "docs/使用说明.md", "使用说明.md"),
        (ROOT / "docs/阶段验收记录.md", "阶段验收记录.md"),
        (ROOT / "validation/windows-exe/interface.png", "界面预览.png"),
        (ROOT / "validation/windows-exe/release-verification.json", "Windows验收结果.json"),
    ):
        shutil.copy2(source, destination / name)
    quickstart = f"""學生證工作室 · Windows x64
交付日期：{date.today().isoformat()}

1. 雙擊 StudentCardStudio.exe，無需另裝 Python。
2. 選擇 .xlsx 名冊、相片目錄、649×1033 原版模板、psd_mask.png 及輸出目錄。字體可選原 ARLRDBD.TTF/BiauKai.ttf/Arial.ttf。
3. 視需要勾選綠幕退底及 3×4 檢閱 PDF，開始製作。
4. 每次建立獨立輸出目錄，內含 single_cards/、cropped_photos/，及選擇生成的 student_cards_review_3x4.pdf。
5. 第二分頁可獨立裁剪 10:13 eClass 相片。相片採資料夾第一層 JPG/PNG，不接受 ZIP。
6. 勾選正背面 PDF 並選擇背面，可產生每人兩頁 PDF 及 All_Students_Combined.pdf；第三分頁可從 single_cards/ 單獨產生 PDF。預設頁幅 54×85.6 mm，可調整。
7. 所有路徑、選項及尺寸自動保存，關閉再開啟仍可還原。這與已移除的 A4 多張雙面拼版不同。

名冊欄位支援 StudentID/學號/ID、Name/姓名、Class/班別、ClassNumber/班號。
學號建議保存為文字；純零數字格式也會保留顯示位數。公式欄位請先轉為值。
先以少量資料檢查模板排版、人像裁剪及中文顯示，再批量製作。

本次可執行檔已核對獨立驗證報告的 SHA256。實際檢查項目見 Windows验收结果.json。
檢閱 PDF 為單面 A4，3 欄 4 列、最多 12 張，並非實尺寸證件印刷檔。

StudentCardStudio-source.zip 包含原始碼、依賴、測試、模型、說明及原生構建腳本。
"""
    (destination / "先读我.txt").write_text(quickstart, encoding="utf-8-sig")
    archive = destination / "StudentCardStudio-windows-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for file in (exe, destination / "先读我.txt", destination / "使用说明.md", destination / "阶段验收记录.md", destination / "Windows验收结果.json", destination / "界面预览.png"):
            output.write(file, file.name)
        output.write(ROOT / "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md")
        for base, prefix in ((ROOT / "assets/licenses", "licenses"), (ROOT / "build/third_party_licenses", "licenses/runtime")):
            for file in sorted(base.rglob("*")):
                if file.is_file():
                    output.write(file, str(Path(prefix) / file.relative_to(base)))
        output.write(ROOT / "assets/YUNET_LICENSE.txt", "licenses/YUNET_LICENSE.txt")
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise RuntimeError("Windows ZIP integrity verification failed")
        if hashlib.sha256(bundle.read(exe.name)).hexdigest() != sha256(exe):
            raise RuntimeError("Windows ZIP executable differs from the tested executable")
    # Keep project release folder and source build metadata consistent with final ZIP.
    shutil.copy2(archive, ROOT / "release" / archive.name)
    metadata_file = ROOT / "release/build-windows-x64.json"
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    metadata.update(sha256=sha256(archive), independent_verification=True, exe_sha256=sha256(exe))
    metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "release" / (archive.name + ".sha256")).write_text(f"{sha256(archive)}  {archive.name}\n", encoding="utf-8")
    source = package(destination / "StudentCardStudio-source.zip", notebook)
    hashes = {file.name: sha256(file) for file in (exe, archive, source)}
    (destination / "SHA256SUMS.txt").write_text("".join(f"{digest}  {name}\n" for name, digest in hashes.items()), encoding="utf-8")
    print(json.dumps({"destination": str(destination), "files": [{"name": file.name, "bytes": file.stat().st_size} for file in (exe, archive, source)], "checksums": hashes}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--notebook", type=Path)
    options = parser.parse_args()
    deliver(options.destination, options.notebook)
