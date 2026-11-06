# 學生證工作室 Student Card Studio

本機 Python／PySide6 桌面工具。名冊、相片及結果在本機處理，正常使用不會上傳學生資料。

## 目前功能

- 繁體中文／英文介面，背景批次處理與進度顯示。
- 讀取 `.xlsx` 第一個工作表，依學號配對 JPG／JPEG／PNG 相片，產生無損 PNG 學生證。
- 恢復原 Colab 的 **649×1033 直式版型**：原廠遮罩合成中央圓形照片、中英文姓名置中、Code128 條碼及學號。
- 保留文字學號前導零，以及 `00000` 這類純零數字格式。公式欄位須先轉成值。
- YuNet 鼻尖／臉寬定位，套用原版 0.32 臉部佔比、340×340 照片區及預設 1.2 亮度。YuNet 不等同原 MTCNN，照片定位不保證像素級相同。
- 獨立 eClass 裁剪恢復 **10:13 最大保留面積**，以人臉作錨點，結果須人工檢查。
- 選用綠幕退底補白；非綠幕會嘗試 GrabCut，一般白底照片建議關閉。
- **3×4 檢閱 PDF**：單面 A4、3 欄 4 列、每頁最多 12 張，保持卡片比例。這是縮放檢閱排版，不是實尺寸證件印刷檔。
- **每人正背面 PDF＋全班總 PDF**：一人兩頁、先正面後背面，無損嵌入圖片；總檔按檔名排序合併個別 PDF。
- **僅生成 PDF 分頁**：可從已有正面圖片目錄產生正背面 PDF，不需重新製卡或載入名冊／人臉模型。
- 自動保留上次三個分頁的路徑、選項、亮度、PDF 尺寸與語言，關閉重開仍可還原。
- 獨立相片裁剪分頁、每次建立新輸出目錄，避免重跑覆寫。

已移除的是 **A4 多張雙面列印排版**，並非每位學生兩頁的正背面 PDF。舊版測試報告不代表本版已通過驗證；目前介面不提供 ZIP 輸入、CSV/JSON 任務報告或參數預覽。

## 輸入與輸出

| 欄位 | 支援名稱（大小寫不敏感） |
|---|---|
| 學號（必要） | `StudentID`、`學號`、`学号`、`ID` |
| 姓名（至少一種） | `Name` 英文、`姓名` 中文分開讀取；中文空白、`/`、`／` 或 `nan` 視為無中文 |
| 班別 | `Class`、`班別`、`班别` |
| 班號 | `ClassNumber`、`學號/班號`、`ClassNo`、`班號`、`班号` |

相片放在指定資料夾第一層，檔名主體與學號一致，例如 `00001.JPG`。不掃描子資料夾、不接受 ZIP。重複學號、多張同學號相片、缺少／損壞相片會列為失敗，其他有效學生繼續處理。

製卡必須使用原版 649×1033 模板及相同尺寸的 `psd_mask.png`，白色為照片區、黑色保留底圖；照片區座標為 `(155,347)`、340×340。遮罩可明確選擇，或自動讀取模板同目錄的原檔；缺少或不合規的遮罩會阻止任務，不再產生錯位卡片。

字體可以在介面選擇，留空時先尋找模板同目錄的 `ARLRDBD.TTF`（英文）、`BiauKai.ttf`（中文）、`Arial.ttf`（學號），找不到則用系統字體，效果可能不同。字體、模板與遮罩不隨應用提供；明確指定但無法載入的字體會報錯，不會靜默替換。

製卡時可選「同時生成每人正背面 PDF 及全班總 PDF」，指定背面圖片；留空會尋找模板同目錄的 `back2026.png`。不勾選時不要求背面。PDF 每頁預設 **54×85.6 mm**，可修改寬／高；圖片等比例置中，不拉伸。實際學校規格與列印縮放請自行確認。

第三分頁「僅生成正背面 PDF」選取 **只含已完成正面卡片**的目錄、背面圖片及輸出目錄即可。不會把資料夾內的既有 PDF 或 3×4 檢閱檔再次合併，也不會把選定背面當成學生正面。產生新的 `pdf_日期時間_識別碼/`。

每次在選定的輸出目錄內建立新的任務子目錄。製卡目錄包含：

```text
single_cards/                  單張原版 PNG 卡片
cropped_photos/                10:13 裁剪相片（未調亮、未去背）
student_cards_review_3x4.pdf    有勾選且生成成功才存在
individual_pdfs/               有勾選時，每位學生一個正背面兩頁 PDF
All_Students_Combined.pdf       所有成功個別 PDF 依檔名排序合併
```

不可把輸出設在來源相片目錄或其子目錄。完成視窗會顯示本次實際輸出路徑；PDF 匯出失敗會警告，不冒充整項任務成功。

設定使用本機 Qt INI 保存，預設 macOS 位置為 `~/.config/StudentCardStudio/StudentCardStudio.ini`。修改後短暫延遲自動保存，開始工作及正常關閉也會保存。只保存路徑和操作選項，不複製名冊、照片或字體；路徑本身仍可能含個人資料。外接磁碟未掛載時會保留記錄，執行任務才檢查是否可讀。自動測試與演示使用隔離設定，不覆寫使用者設定。

## 從原始碼執行

建議 Python 3.11–3.13；本機亦驗證 Python 3.9.6。依賴使用相容版本範圍而非全平台鎖定檔。

macOS：

```bash
cd /Users/logan/Downloads/StudentCardStudio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python main.py
```

Windows 使用虛擬環境的 `Scripts/python.exe` 執行相同 Python 命令。只執行應用可安裝 `requirements.txt`。

## 驗證與打包

```bash
python -m pytest -q
python main.py --smoke-test verification/manual_smoke
python scripts/verify_release.py --smoke-dir verification/manual_smoke
python scripts/build.py
```

打包腳本先執行測試及原始碼演示，再執行 PyInstaller 與打包版演示；只能在目標系統原生構建。Mac 產物為 `dist/StudentCardStudio.app`，Windows 預設為單檔 exe；可用 `--windows-onedir` 改為目錄版。

額外獨立驗證使用 `scripts/verify_release.py --executable <可執行檔> --smoke-dir <驗證目錄>`，會在另一工作目錄、移除 Python 環境變數後啟動應用，檢查檔案、3×4 PDF、每人與總檔正背面頁序／無損內容／頁幅、裁剪比例及截圖。

雲端工作流程位於 `.github/workflows/build.yml`。本機設定存在不代表遠端已執行；簽名、公證及實際設備操作須另外驗證。詳見 `docs/Mac云端打包.md`。

## 結構

```text
main.py             GUI 入口與離線演示
student_card/       GUI、核心、影像處理、虛構演示資料
assets/             YuNet 模型、圖示及授權
tests/              目前介面的回歸測試與離線人像
scripts/            打包、驗證與交付工具
docs/               使用說明、介面契約、歷史紀錄與原 Notebook
```

學校模板與真實學生資料不隨程式提供。字體從本機取得，不複製系統字體。本版固定使用原 Colab 版型，不支援任意長寬模板；先用少量資料核對排版與中文顯示。其他使用說明見 `docs/使用说明.md`；第三方資訊見 `THIRD_PARTY_NOTICES.md`。