# 学生证工作室 Student Card Studio

将 `Batch_Student_Card_FINAL.ipynb` 的学生证制作、双面 PDF 和 eClass 照片裁剪流程转换为本地 Python 桌面程序。学生名单、照片和生成结果在本机处理；运行程序不需要 Colab、网络或安装 Python。

## 发行包

本次按用户确认先交付 Windows 应用和源码包；Mac 云端构建留待后续执行。项目已附 Mac 构建配置，当前没有创建远程仓库，也没有产出或验收 Mac `.app`。

- Windows：解压 `StudentCardStudio-windows-x64.zip`，双击 `StudentCardStudio.exe`。
- Mac M 系列：使用 `StudentCardStudio-macos-arm64.zip`；Intel Mac 使用 `StudentCardStudio-macos-x64.zip`。解压后把 `StudentCardStudio.app` 拖入“应用程序”。
- Mac 需要通过 macOS 环境实际构建。源码内的工作流是构建方案，不能当作已构建成功的 Mac 安装包；实际交付及验证状态见 [阶段验收记录](docs/阶段验收记录.md)。
- 未进行 Developer ID 签名和 Apple 公证的 Mac 测试版，可能被 Gatekeeper 拦截；正式分发的处理见 [Mac 云端打包](docs/Mac云端打包.md)。
- 当前锁定的依赖要求：Windows 10/11 x64；Mac 依赖最低 macOS 14（云端目标 macOS 15）。其他系统版本未经承诺。

首次使用建议先点击“载入演示资料”，再点击“检查资料”，选择虚构学生预览并运行。之后替换为学校实际素材。演示资料不代表原学校学生证的真实版式。

## 功能

1. 学生证：检查 Excel 和照片匹配情况，预览单个学生，按原 Notebook 默认坐标生成 PNG；中文姓名可为空，长姓名自动适配。
2. PDF：生成每人两页 PDF 和全班合并 PDF，正面、背面交替，按学号排序；页面实际尺寸可设置。
3. eClass：递归处理照片文件夹或 ZIP，按人脸位置裁为 10:13。
4. 任务记录：每次建立独立输出目录，生成处理明细、任务清单和 ZIP；未检测到人脸、多人、缺照片、损坏文件等会明确报告。

详细输入要求、预览调整与常见问题见 [使用说明](docs/使用说明.md)。

## 从源码运行

建议使用 Python 3.13 和独立虚拟环境。系统字体由本机发现，也可在程序中手动指定合法持有的字体文件；源码和发行包不附带 Windows/macOS 专有字体。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
```

macOS Terminal：

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python main.py
```

如果只运行源码，可安装 `requirements.txt`。`requirements-dev.txt` 另含构建和测试工具。

## 验证与打包

```bash
python -m pytest -q
python main.py --smoke-test verification/manual_smoke
python scripts/build.py
python scripts/verify_release.py --executable dist/StudentCardStudio.exe --smoke-dir verification/independent_release
```

`build.py` 默认先运行测试，再执行源码演示、打包、发行版演示，全部成功才生成 `release/` 内的 ZIP、SHA256 和构建记录。`--skip-tests` 仅用于当前源码已经通过同一套测试的重复构建，源码和发行版 smoke check 仍会执行。打包只能在目标系统原生执行：Windows 构建 exe，macOS 构建 app。[PyInstaller 官方说明](https://www.pyinstaller.org/en/stable/)

`verify_release.py` 是额外的独立验收，使用另一进程和工作目录，移除 PATH 中的 Python，逐张解码条码、核对 PDF 页序与物理尺寸、照片比例和清单。上例为 Windows 路径；Mac 对应可执行文件为 `dist/StudentCardStudio.app/Contents/MacOS/StudentCardStudio`。

云端打包配置位于 `.github/workflows/build.yml`，使用 GitHub Actions 的 Windows、Apple Silicon Mac 和 Intel Mac 三类环境。账号、仓库和云端执行情况均以实际授权和运行结果为准。参见 [Mac 云端打包](docs/Mac云端打包.md)。

## 项目结构

```text
main.py                    启动入口及离线 smoke check
student_card/              桌面界面、核心处理、人脸定位和演示资料
assets/                    随程序分发的 YuNet 模型与资源
tests/                     独立功能验证
scripts/build.py           原生打包与发行版检查
.github/workflows/build.yml 双端云端构建
docs/                      使用说明、Mac构建说明、阶段验收记录
```

原 Notebook 保留在原位置，不会被程序修改；原学校底图、遮罩、字体、背面和真实名单需要使用者自行选择。

第三方软件和模型的来源及许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
