# 網站維護說明

這個網站是 GitHub Pages 靜態站（`main` 分支根目錄），用 Tailwind CDN。`blog/` 是用腳本產生的，**不要直接手改 `blog/` 裡的檔案**。

## 網站結構
| 頁面 | 檔案 | 說明 |
|---|---|---|
| 首頁 | `index.html` | 手寫。一句話介紹與「關於我」、專業服務（目前是預留空位）。不放部落格內容，履歷與部落格從導覽列進入 |
| 我的專長（履歷） | `resume.html` | 手寫。身份背景、職責貢獻、專業技能、核心優勢 |
| 我的作品（作品集） | `portfolio/index.html` | 手寫。目前是「整理中」，檔案內的 HTML 註解有作品卡片範本；截圖放 `portfolio/img/` |
| 專業服務 | `index.html` 的 `#services` 區塊 | 目前只有「服務項目準備中」的預留空位，之後在這裡放服務項目卡片 |
| 部落格 | `blog/` | 腳本產生 |

導覽列在 `index.html`、`resume.html`、`portfolio/index.html` 各自手寫一份，部落格頁面的導覽列寫在 `tools/build_blog.py` 的 `HEAD`。新增或改名頁面時，這四處要一起改。

首頁受眾是求職與合作對象，部落格則是純興趣、研究與生活分享。

## 重新產生部落格
```
pip install markdown-it-py
python3 tools/build_blog.py
```
- 文章資料：`tools/posts.json`（欄位：id、date、category、title、md、media）
- 設定：`tools/blog_config.json`
  - `hidden_ids`：不顯示的文章 id（網站上會消失，但 posts.json 裡仍有資料）
  - `category_labels`：分類顯示名稱（例如「未分類」顯示為「早期舊文」）
  - `category_order`：分類排序
- 腳本只會重建 `blog/index.html` 和 `blog/posts/*.html`，不會動首頁。

## 新增一篇文章
在 `tools/posts.json` 加一筆：`id`（不可重複的整數）、`date`（YYYY-MM-DD）、`category`、`title`、`md`（內文，一行一段，空行用 `<empty-block/>`）、`media`（略過的圖片數，沒有填 0）。再執行上面的建置指令。

## 注意
- 這個儲存庫是公開的：token、密碼、不能公開的原始碼、有版權疑慮的素材一律不要放進來。
- 網站上不放電話、地址、身分證件等個人資料，也先不放 email（避免被亂寄信）。要加聯絡方式前先問過本人。
- 網址區分大小寫：`https://jpking7055.github.io/mySite/`
- 舊文的圖片與影片沒有搬過來。
