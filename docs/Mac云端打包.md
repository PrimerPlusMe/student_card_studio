# 没有 Mac 的情况下构建 Mac App

本项目通过 GitHub Actions 的 macOS runner 构建真实 `.app`。这一步需要有权使用的 GitHub 仓库和 Actions；本地存在配置文件不代表云端已经运行。GitHub 当前提供 Apple Silicon 和 Intel 的 macOS 环境，分别使用 `macos-15` 和 `macos-15-intel`。[GitHub 官方文档](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

当前状态：用户已确认本次先完成 Windows 应用与源码包，Mac 云端构建稍后进行。没有创建远程仓库，没有运行云端作业，没有 Mac `.app` 产物。以下为后续构建步骤。

## 运行构建

1. 将源码包解压后的项目内容放在一个 GitHub 仓库根目录，包括隐藏的 `.github/`。不要上传真实学生名单、照片、输出目录、证书或个人配置。
2. 打开仓库 Actions，选择 `Build Windows and macOS apps`，点击 `Run workflow`。也可推送以 `v` 开头的版本标签触发。
3. 三个构建任务分别安装固定版本依赖、运行测试、执行源码离线演示、打包原生应用、执行打包版离线演示。
4. 所有步骤通过后，在该次运行的 Artifacts 下载对应 ZIP。每个发行件含 SHA256；验证证据单独保存为 `verification-...`。
5. Mac 应用必须解压 ZIP 后运行。项目用 `ditto` 创建 ZIP，保留 `.app` 的可执行权限与链接；不要直接把 `.app` 文件夹拖入 `upload-artifact` 代替归档。

项目依赖的最低共同 macOS 版本为 14；配置的云端构建和自动验证系统为 macOS 15。构建成功只能证明在该 runner 上通过检查，不代表所有 Mac 版本或打印机均已测试。发给实际使用者前，应检查文件选择、中文字体、真实素材排版、正反面 PDF 和打印。

## 测试分发与正式分发

默认构建不使用 Developer ID 证书，也不向 Apple 提交公证，属于内部测试包。macOS 可能阻止打开；只有确认来源且机构策略允许时，使用者才可按 Apple 文档在“系统设置 → 隐私与安全性”中处理。无需也不建议全局关闭 Gatekeeper。[Apple 打开应用说明](https://support.apple.com/en-us/102445)

若要正式发给多人使用，应使用 Apple Developer Program 的 Developer ID 证书签名并提交 Apple 公证。打包脚本接受当前 Mac keychain 中已有的签名身份：

```bash
export MACOS_SIGNING_IDENTITY='Developer ID Application: Your Organization (TEAMID)'
python scripts/build.py
```

自动工作流当前不导入证书、不读取 Apple 账号，也不默认完成公证。需要正式签名时，应在自己的 Actions Secrets 配置证书和认证资料，并在受控 macOS 环境导入 keychain，再运行上述构建。不要把证书和密码写进源码。

签名后可使用 `xcrun notarytool submit ... --wait` 提交，用 `xcrun stapler staple StudentCardStudio.app` 附加公证票据，重新用 `ditto` 归档，并用 `codesign --verify --deep --strict` 与 `spctl --assess --type execute` 检查。公证成功后，需更新发行记录中的 `notarized` 状态并重新计算 ZIP 校验值。[Apple Developer ID](https://developer.apple.com/developer-id/)、[Apple 公证流程](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)

## 失败排查

- 安装依赖失败：先确认源码没有改动固定版本清单；工作流强制使用 wheel，避免 Intel Mac 意外现场编译原生库。
- 人脸模型缺失：确认 `assets/face_detection_yunet_2023mar.onnx` 已随源码提交，且不是 Git LFS 文本指针。
- 构建通过但打开失败：查看验证证据和系统弹窗，区分缺少运行库、架构不匹配、系统版本不支持与 Gatekeeper 拦截。
- 云端资源额度不足：查看自己账号的 Actions 用量和计费设置；配额和费用以 GitHub 账号实际显示为准。
