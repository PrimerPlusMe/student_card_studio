"""Assemble the reviewed Windows application and source into a delivery folder."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from package_source import package

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def deliver(destination: Path, notebook: Path | None = None):
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    report = json.loads((ROOT / "validation/windows-exe/release-verification.json").read_text(encoding="utf-8"))
    if report.get("passed") is not True:
        raise RuntimeError("The executable has not passed independent release validation")
    executable = ROOT / "dist/StudentCardStudio.exe"
    exe = destination / executable.name
    shutil.copy2(executable, exe)
    for source, name in (
        (ROOT / "docs/使用说明.md", "使用说明.md"),
        (ROOT / "docs/阶段验收记录.md", "阶段验收记录.md"),
        (ROOT / "validation/windows-exe/interface.png", "界面预览.png"),
        (ROOT / "validation/windows-exe/release-verification.json", "Windows验收结果.json"),
    ):
        shutil.copy2(source, destination / name)
    quickstart = """学生证工作室 v1.0.0 · Windows x64
交付日期：2026-11-01

1. 双击 StudentCardStudio.exe，无需安装 Python。
2. 首次运行可点击“载入演示资料”→“检查资料”→选择学生→“预览”→“开始生成学生证”。
3. 实际制作请选择自己的 Excel、按学号命名的照片、正面底图、遮罩及背面；字体可自动使用本机字体或自行选择。
4. 可分别制作学生证、合并正反面 PDF、裁剪 eClass 10:13 照片。照片支持文件夹或 ZIP。
5. 任务结束后点“打开输出”，查看图片、PDF、processing_report.csv、manifest.json 和 results.zip。

初始参考画布 648×1050、PDF 成品 54×85.6 mm 均可调整，不代表已确认学校原版规格。
原目录只有 Notebook，学校真实底图、遮罩、字体、名单和照片未包含在此应用中；请先预览后批量制作。

验收：第一阶段 26 项通过，第二阶段最终 42 项通过；打包版在移除 Python 路径、其他工作目录下独立运行并验收通过。
Mac：源码已附 Apple 芯片与 Intel 云端构建配置，按用户要求稍后继续；本次没有生成或验证 Mac .app。

StudentCardStudio-source.zip 包含源码、依赖清单、测试、内置模型、中文说明和双端构建脚本。
其中 docs/original/ 中的原 Notebook 副本已移除执行输出，原始文件未被改动。
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
