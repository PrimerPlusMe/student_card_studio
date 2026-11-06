# Mac 與 Windows 原生打包

工作流程位於 `.github/workflows/build.yml`，設定 Windows、Apple Silicon Mac 和 Intel Mac 三種目標。設定存在不代表遠端構建已執行或成功；以實際 Actions 紀錄及本次產物驗證為準。

## 本機

在目標作業系統的虛擬環境安裝 `requirements-dev.txt`，執行 `python scripts/build.py`。

流程：目前版本 pytest → 原始碼 smoke → PyInstaller → 打包版 smoke → ZIP、SHA256、構建資訊。`--skip-tests` 只適合已對當前程式通過測試的重複構建。

Mac 產物為 `.app`；Windows 為 exe，`--windows-onedir` 可產生目錄版。不可跨作業系統直接編譯另一平台的可執行檔。

可另用 `scripts/verify_release.py --executable ... --smoke-dir ...` 獨立驗證。Windows 正式交付腳本會核對這份報告的可執行檔 SHA256，舊版報告不可沿用。

## 雲端

1. 提交程式、資源及測試，不要加入真實學生資料、私密設定或憑證。
2. 透過 Actions 手動觸發或推送 `v` 開頭標籤。
3. 只有全部測試和打包版演示完成的任務才可作為成功構建。
4. 取得 ZIP 及驗證證據，並在實際使用設備檢查開啟、檔案選擇、中文、真實模板和檢閱 PDF。

依賴使用版本範圍，非逐平台鎖定；每次構建收集實際套件版本與授權。新平台／新依賴組合仍須重跑全部驗證。

## 簽名與公證

預設不使用 Apple Developer ID、不執行公證，僅適合受控測試分發。正式分發須另行設定受控憑證、簽名及公證，不要把憑證或密碼加入程式庫。

打包腳本可從 `MACOS_SIGNING_IDENTITY` 讀取本機鑰匙圈既有身份；公證仍須另外提交並驗證。構建通過不等於已簽名、公證或通過所有設備的互動測試。不要為執行測試包而全域關閉系統安全保護。