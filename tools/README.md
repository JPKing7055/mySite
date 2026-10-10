# 網站維護說明

這個網站是 GitHub Pages 靜態站（`main` 分支根目錄）。首頁 `index.html` 是手寫的單頁（Tailwind CDN）；`blog/` 是用腳本產生的，**不要直接手改 `blog/` 裡的檔案**。

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
- 腳本會重建 `blog/index.html`、`blog/posts/*.html`，並更新首頁 `index.html` 裡 `BLOG-LATEST:START ~ END` 之間的最新文章區塊。

## 新增一篇文章
在 `tools/posts.json` 加一筆：`id`（不可重複的整數）、`date`（YYYY-MM-DD）、`category`、`title`、`md`（內文，一行一段，空行用 `<empty-block/>`）、`media`（略過的圖片數，沒有填 0）。再執行上面的建置指令。

## 注意
- 這個儲存庫是公開的：token、密碼、不能公開的原始碼、有版權疑慮的素材一律不要放進來。
- 網址區分大小寫：`https://jpking7055.github.io/mySite/`
- 舊文的圖片與影片沒有搬過來。
