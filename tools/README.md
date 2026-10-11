# 網站維護說明

這個網站是 GitHub Pages 靜態站（`main` 分支根目錄），用 Tailwind CDN。`blog/` 是用腳本產生的，**不要直接手改 `blog/` 裡的檔案**。

## 網站結構
| 頁面 | 檔案 | 說明 |
|---|---|---|
| 首頁 | `index.html` | 手寫。品牌區、研究與服務方向（4 張卡片）、成員（JP）、專業服務（目前是預留空位）。不放部落格內容，其他頁面從導覽列進入 |
| 成員專長（履歷） | `resume.html` | 手寫。身份背景、職責貢獻、專業技能、核心優勢 |
| 成員作品（作品集） | `portfolio/index.html` | 手寫。目前是「整理中」，檔案內的 HTML 註解有作品卡片範本；截圖放 `portfolio/img/` |
| 專業服務 | `index.html` 的 `#services` 區塊 | 目前只有「服務項目準備中」的預留空位，之後在這裡放服務項目卡片 |
| 成員個人空間（部落格） | `blog/` | 腳本產生。第一頁「JP 的個人空間」＝「現在在做的事」大區塊＋便條紙牆（每張便條紙是一個專區）；`blog/zone/*.html` 是各專區內頁；`blog/all.html` 是全部文章（搜尋、分類篩選）；`blog/posts/*.html` 是文章 |

成員專長、成員作品兩頁的大標用成員代稱（現在是「JP 的專長」「JP 的作品」），不要跟導覽列文字重複；之後每位成員各有一組頁面時，也照這個命名。

導覽列在 `index.html`、`resume.html`、`portfolio/index.html` 各自手寫一份，部落格頁面的導覽列寫在 `tools/build_blog.py` 的 `HEAD`。新增或改名頁面時，這四處要一起改。

品牌名是「JPK Lab」（遊戲化思維實驗室）。成員只用代稱（目前只有 JP），不放本名。首頁受眾是合作與服務對象，部落格則是純興趣、研究與生活分享。新增成員時，複製首頁 `#members` 裡的 `<article>` 卡片即可。

## 個人空間的版面設定（`tools/blog_config.json`）
- `now`：「現在在做的事」區塊。`paragraphs` 第一段是大字，之後的段落是內文；`updated` 是顯示的更新日期（改內容時一起改）。
- `zones`：便條紙牆。每個專區有 `slug`（網址用）、`name`、`categories`（哪些文章分類屬於這個專區）、`color`（便條紙底色）、`summary`（便條紙上的摘要）。順序就是顯示順序。沒有文章的專區會顯示成不能點的便條紙「尚無文章」，有文章後自動變成可點，並產生內頁。
- 文章分類不在任何專區時，建置會印出 WARNING，文章仍會出現在 `all.html`，但便條紙牆看不到，要補一個專區。
- 目前專區：虛擬歌手創作、運動健身、外語學習、生活記事、碎碎唸、專業學習、遊戲試玩、舊文存檔（對應「未分類」）。

## 從 Notion 同步新文章
Notion 資料庫「部落格文章」（在「我的簡介」頁面下）是寫作的地方，網站是從它產生的。作業流程：
1. 本人在 Notion 寫文章，填好 `分類`（要是上面專區對應的分類之一）、`發布日期`，把 `狀態` 設成「待發布」，`來源` 選 Notion。
2. 本人告訴 Claude「同步 Notion」。
3. Claude 查詢 `狀態` = 待發布 的頁面，逐頁讀內容，轉成 `posts.json` 的格式（一行一段、空行用 `<empty-block/>`、圖片略過並累計 `media`），`id` 取目前最大值加 1，並加一個 `notion` 欄位記錄 Notion 頁面 ID（之後改文章靠它對應）。
4. 執行建置、檢查、提交、推送。
5. 推送成功後，回到 Notion 把該篇 `狀態` 改成「已發布」，`文章網址` 填網站上的網址。
- 改已發布的文章：本人說是哪一篇，Claude 用 `notion` 欄位找到對應的 `posts.json` 項目重新轉換。
- 新增分類：Notion 的 `分類` 選項、`blog_config.json` 的 `zones` 與 `category_order` 三處要一起加。
- 舊的 `初音V家`、`虛擬創作` 分類已合併成「虛擬歌手創作」，Notion 裡這兩個選項沒有文章了。

## 重新產生部落格
```
pip install markdown-it-py
python3 tools/build_blog.py
```
- 文章資料：`tools/posts.json`（欄位：id、date、category、title、md、media）
- 設定：`tools/blog_config.json`
  - `hidden_ids`：不顯示的文章 id（網站上會消失，但 posts.json 裡仍有資料）。**儲存庫是公開的，不想讓人看到的文章不要放進 posts.json**，私人文章只留在 Notion（狀態不要設「待發布」）
  - `category_labels`：分類顯示名稱（例如「未分類」顯示為「早期舊文」）
  - `category_order`：分類排序
- 腳本會重建 `blog/` 底下的 `index.html`、`all.html`、`zone/*.html`、`posts/*.html`，不會動首頁和其他頁面。

## 新增一篇文章
在 `tools/posts.json` 加一筆：`id`（不可重複的整數）、`date`（YYYY-MM-DD）、`category`、`title`、`md`（內文，一行一段，空行用 `<empty-block/>`）、`media`（略過的圖片數，沒有填 0）。再執行上面的建置指令。

## 注意
- 這個儲存庫是公開的：token、密碼、不能公開的原始碼、有版權疑慮的素材一律不要放進來。
- 網站上不放電話、地址、身分證件等個人資料，也先不放 email（避免被亂寄信）。要加聯絡方式前先問過本人。
- 網址區分大小寫：`https://jpking7055.github.io/mySite/`
- 舊文的圖片與影片沒有搬過來。
