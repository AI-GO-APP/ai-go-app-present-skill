# ai-go-app-present-skill

把 AI GO custom app 做成 **16:9 閱讀式簡報 PDF 操作手冊**的 Agent Skill：
抓重點功能 → 規劃結構（使用者核准）→ 登入真實後台截圖（全頁圖解＋局部操作）→
查證每個設定「情境 → 結果」→ 排版輸出 → 逐頁目視驗收。

適用：客服後台、CRM、POS、ERP 等任何掛在 AI GO runtime 或 developer 預覽頁的 app。

## 安裝

```bash
# 專案內（或 ~/.claude/skills/ 供全域使用）
git clone https://github.com/AI-GO-APP/ai-go-app-present-skill.git .claude/skills/ai-go-app-present
cd .claude/skills/ai-go-app-present
npm install            # puppeteer-core
pip install pillow     # 總表
```

- Claude Code：放進 `.claude/skills/` 即可被觸發（說「幫 XX 做操作手冊」）
- 其他 agent：把 `SKILL.md` 與 `references/` 加進 rules／context

## 憑證

不放在 repo 裡。擇一：

| 模式 | 需要 |
|---|---|
| runtime（已安裝在租戶的 app） | `AIGO_EMAIL`／`AIGO_PASSWORD`，或 `AIGO_TOKEN` |
| preview（developer 預覽頁） | `DEVPORTAL_PAT` |

放環境變數，或放在 `present.config.json` 的 `env_file` 指向的檔案（預設 `~/.aigo/.env`）。

## 用法

見 [SKILL.md](SKILL.md) 的「快速開始」。完整流程與關卡在 [references/workflow.md](references/workflow.md)。

## 產出長什麼樣

- 封面 → 導讀 → 後台地圖 → 前置設定
- A 核心工作：全景圖解、找資料、狀態機、一個流程一頁、讀懂系統資訊、側欄面板、每天的節奏
- B 控制 AI：控制點地圖、每組參數「設定（目前值）｜情境 → 結果」、測試方法、症狀 → 改哪裡
- C 其他與維護：其他頁面、維護節奏、目前設定值附錄

## 版本

見 [CHANGELOG.md](CHANGELOG.md)。
