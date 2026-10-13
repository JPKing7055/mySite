#!/usr/bin/env python3
"""從 Notion 同步網站內容：
1. 「部落格文章」資料庫 → tools/posts.json，文章裡的圖片存進 blog/img/。
2. 「作品」資料庫 → tools/works.json（成員作品頁），作品頁裡的圖片存進 portfolio/img/。

部落格文章的規則（完整說明見 tools/README.md）：
- 狀態＝「待發布」且還不在 posts.json 的頁面 → 新增。
- 已在 posts.json（有 notion 欄位）、狀態是「待發布」或「已發布」的頁面 → 在 Notion 被編輯過就更新，
  或用環境變數 RESYNC 指定（例如 "688,705" 或 "all"）強制重新同步。
- 其他頁面（例如只留在 Notion 的舊文、私人文章）一律不會被加進來。

作品的規則：
- 「網站顯示」是「待發布」或「已發布」的作品會出現在網站，每次同步都以 Notion 為準整批重建 works.json。
- 改成「草稿」（或刪掉）的作品，下次同步就會從網站拿掉，它的圖片也會一併清掉。
- 作品資料庫讀不到時（例如還沒把整合加進資料庫），works.json 維持原樣，只在 Summary 提醒。

唯讀：這個腳本只讀 Notion，不會改 Notion 的任何內容。

環境變數：
  NOTION_TOKEN            必填。Notion 內部整合的金鑰（放在 GitHub Secrets，不要寫進程式）
  NOTION_DATA_SOURCE_ID   選填。預設是「部落格文章」資料來源
  NOTION_WORKS_DATA_SOURCE_ID  選填。預設是「作品」資料來源
  NOTION_VERSION          選填。預設 2025-09-03
  RESYNC                  選填。逗號分隔的文章 id，或 all
  SYNC_ROOT               選填。專案根目錄（測試用）
  GITHUB_STEP_SUMMARY     GitHub Actions 自動提供，摘要會寫到這裡

只用標準函式庫＋Pillow。日誌只印文章標題與圖片檔名，不印內文、金鑰或圖片網址
（Notion 圖片網址帶簽名，而且儲存庫是公開的，日誌任何人都看得到）。
"""
import io
import json
import os
import re
import shutil
import sys
import time
import hashlib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("SYNC_ROOT") or Path(__file__).resolve().parent.parent)
POSTS_PATH = ROOT / "tools" / "posts.json"
WORKS_PATH = ROOT / "tools" / "works.json"
CFG_PATH = ROOT / "tools" / "blog_config.json"
IMG_DIR = ROOT / "blog" / "img"
WORKS_IMG_DIR = ROOT / "portfolio" / "img"

DATA_SOURCE = os.environ.get("NOTION_DATA_SOURCE_ID", "89785077-cd87-4fbd-b55a-53b0631df9a7")
WORKS_DATA_SOURCE = os.environ.get("NOTION_WORKS_DATA_SOURCE_ID", "43db433a-787f-4682-8193-17920774bbed")
NOTION_VERSION = os.environ.get("NOTION_VERSION", "2025-09-03")

P_TITLE, P_CATEGORY, P_STATUS, P_DATE = "標題", "分類", "狀態", "發布日期"
S_PUBLISH, S_LIVE = "待發布", "已發布"

# 作品資料庫的欄位名稱
W_TITLE, W_SUMMARY, W_PROGRESS, W_SHOW = "作品名稱", "一句話說明", "專案進度", "網站顯示"
W_SLUG, W_TAGS, W_ORDER = "網址代稱", "技術與工具", "顯示順序"
W_LIVE, W_GITHUB, W_RELATED = "成品連結", "GitHub 連結", "相關文章"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,59}$")
RESERVED_SLUGS = {"index", "img"}

MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_WIDTH = 1600
TARGET_BYTES = 1024 * 1024
# 與 build_blog.py 相同：單獨一行的 [圖:檔名|圖說]
IMG_RE = re.compile(r"^\[圖[:：]\s*([A-Za-z0-9_.\-]+\.(?:png|jpe?g|gif|webp))\s*(?:[|｜]\s*([^\]]*))?\]$", re.I)


class SyncError(Exception):
    pass


# ───────────────────────── 網路 ─────────────────────────

def notion(method, path, body=None):
    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token:
        raise SyncError("找不到 NOTION_TOKEN。請到 GitHub 儲存庫 Settings → Secrets and variables → Actions 新增。")
    url = "https://api.notion.com/v1" + path
    data = json.dumps(body).encode("utf8") if body is not None else None
    last = ""
    for attempt in range(6):
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + token,
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                last = f"HTTP {e.code}"
                time.sleep(float(e.headers.get("Retry-After") or 2 * (attempt + 1)))
                continue
            msg = e.read().decode("utf8", "replace")[:300]
            raise SyncError(f"Notion API 回應 {e.code}（{method} {path.split('?')[0]}）：{msg}")
        except urllib.error.URLError as e:
            last = type(e).__name__
            time.sleep(2 * (attempt + 1))
    raise SyncError(f"Notion API 連線失敗（{method} {path.split('?')[0]}）：{last}")


def http_get(url):
    """下載圖片。不帶任何金鑰（Notion 的圖片網址本身就帶簽名）。錯誤訊息不含網址。"""
    if not url.lower().startswith("https://"):
        raise SyncError("只允許 https 圖片網址")
    req = urllib.request.Request(url, headers={"User-Agent": "jpklab-sync/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read(MAX_IMAGE_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise SyncError(f"下載失敗 HTTP {e.code}")
    except Exception as e:
        raise SyncError(f"下載失敗 {type(e).__name__}")
    if len(data) > MAX_IMAGE_BYTES:
        raise SyncError("圖片超過 25MB")
    return data


def list_children(block_id):
    out, cursor = [], None
    while True:
        q = f"/blocks/{block_id}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
        r = notion("GET", q)
        out += r.get("results", [])
        if not r.get("has_more"):
            return out
        cursor = r.get("next_cursor")


def all_pages(data_source=None):
    data_source = data_source or DATA_SOURCE
    pages, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = notion("POST", f"/data_sources/{data_source}/query", body)
        pages += r.get("results", [])
        if not r.get("has_more"):
            break
        cursor = r.get("next_cursor")
    return [p for p in pages if not (p.get("in_trash") or p.get("archived"))]


# ───────────────────────── 屬性 ─────────────────────────

def prop_title(page, name=None):
    p = (page.get("properties") or {}).get(name or P_TITLE) or {}
    return "".join(r.get("plain_text", "") for r in p.get("title", [])).strip()


def prop_select(page, name):
    p = (page.get("properties") or {}).get(name) or {}
    s = p.get("select")
    return s.get("name") if s else None


def prop_date(page, name):
    p = (page.get("properties") or {}).get(name) or {}
    d = p.get("date")
    return d["start"][:10] if d and d.get("start") else None


def prop_text(page, name):
    p = (page.get("properties") or {}).get(name) or {}
    return "".join(r.get("plain_text", "") for r in p.get("rich_text", [])).strip()


def prop_multi(page, name):
    p = (page.get("properties") or {}).get(name) or {}
    return [o["name"].strip() for o in p.get("multi_select", []) if o.get("name", "").strip()]


def prop_number(page, name):
    p = (page.get("properties") or {}).get(name) or {}
    return p.get("number")


def prop_url(page, name):
    p = (page.get("properties") or {}).get(name) or {}
    return (p.get("url") or "").strip()


def prop_relation_ids(page, name):
    p = (page.get("properties") or {}).get(name) or {}
    return [r["id"] for r in p.get("relation", []) if r.get("id")]


# ───────────────────────── 文字轉 Markdown ─────────────────────────

def esc_text(s):
    s = s.replace("\\", "\\\\")
    return re.sub(r"([*_`~\[\]<>])", r"\\\1", s)


def link_ok(href):
    if not href or not re.match(r"^https?://", href):
        return False
    host = re.match(r"^https?://([^/:?#]+)", href).group(1).lower()
    return not (host.endswith("notion.so") or host.endswith("notion.com"))  # 私人頁面連結不輸出


def safe_url(u):
    return u.replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def rt_seg(rt):
    t = rt.get("plain_text", "")
    a = rt.get("annotations") or {}
    plain = lambda x: esc_text(x).replace("\n", "<br>")
    core = t.strip()
    if not core:
        return plain(t)
    lead, trail = t[:len(t) - len(t.lstrip())], t[len(t.rstrip()):]
    if a.get("code") and "`" not in core and "\n" not in core:
        body = "`" + core + "`"
    else:
        body = plain(core)
        # 用 HTML 標籤而不是 ** ，避免中文緊接符號時 Markdown 判斷失敗
        if a.get("bold"):
            body = "<strong>" + body + "</strong>"
        if a.get("italic"):
            body = "<em>" + body + "</em>"
    if link_ok(rt.get("href")):
        body = f"[{body}]({safe_url(rt['href'])})"
    return plain(lead) + body + plain(trail)


def rt_md(rts):
    return "".join(rt_seg(r) for r in rts or [])


def guard(line):
    """避免一般文字被內文解析器誤認成標題、清單或分隔線。"""
    if re.match(r"^#{1,3} ", line):
        return "\\" + line
    if re.match(r"^- ", line):
        return "\\" + line
    m = re.match(r"^(\d+)\. ", line)
    if m:
        return f"{m.group(1)}\\. " + line[m.end():]
    if line.startswith("---"):
        return "\\" + line
    return line


# ───────────────────────── 圖片 ─────────────────────────

def process_image(data, stem, img_dir=None):
    """縮到 1600px 內、移除 EXIF（含 GPS）、壓到約 1MB；回傳存好的檔名。"""
    from PIL import Image, ImageOps
    img_dir = img_dir or IMG_DIR
    im = Image.open(io.BytesIO(data))
    fmt = (im.format or "").upper()
    img_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "GIF" and getattr(im, "n_frames", 1) > 1:  # 動圖：保留原檔
        if len(data) > 8 * 1024 * 1024:
            raise SyncError("動圖超過 8MB")
        name = stem + ".gif"
        (img_dir / name).write_bytes(data)
        return name
    im = ImageOps.exif_transpose(im)
    if im.width > MAX_WIDTH:
        im = im.resize((MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)), Image.LANCZOS)
    has_alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
    if has_alpha:
        name = stem + ".png"
        im.convert("RGBA").save(img_dir / name, "PNG", optimize=True)
        return name
    rgb = im.convert("RGB")
    name = stem + ".jpg"
    for quality, width in ((85, MAX_WIDTH), (75, MAX_WIDTH), (72, 1280)):
        cur = rgb if rgb.width <= width else rgb.resize((width, round(rgb.height * width / rgb.width)), Image.LANCZOS)
        buf = io.BytesIO()
        cur.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        if buf.tell() <= TARGET_BYTES:
            break
    (img_dir / name).write_bytes(buf.getvalue())
    return name


def save_image(prefix, url, img_dir=None):
    """prefix：文章是 p{id}，作品是 w-{slug}。同一張圖網址（去掉簽名）固定同一個檔名。"""
    img_dir = img_dir or IMG_DIR
    key = hashlib.sha1(url.split("?")[0].encode("utf8")).hexdigest()[:8]
    stem = f"{prefix}-{key}"
    existing = sorted(img_dir.glob(stem + ".*")) if img_dir.exists() else []
    if existing:
        return existing[0].name
    return process_image(http_get(url), stem, img_dir)


# ───────────────────────── 區塊轉文章 ─────────────────────────

SKIP_TYPES = {"child_page", "child_database", "link_to_page", "table_of_contents", "breadcrumb",
              "equation", "template", "unsupported", "ai_block", "meeting_notes", "transcription"}


class Conv:
    def __init__(self, post_id, img_dir=None):
        self.post_id = post_id
        # 圖檔名前綴：文章是 p{id}，作品傳進來的是 "w-{slug}"
        self.prefix = post_id if isinstance(post_id, str) else f"p{post_id}"
        self.img_dir = img_dir
        self.lines, self.notices, self.used = [], [], set()
        self.media = 0

    def note(self, msg):
        if msg not in self.notices:
            self.notices.append(msg)

    def walk(self, blocks):
        for b in blocks:
            t = b.get("type")
            d = b.get(t) or {}
            rich = d.get("rich_text") or []
            txt = rt_md(rich)
            plain = "".join(r.get("plain_text", "") for r in rich).strip()
            if t == "paragraph":
                if not plain:
                    self.lines.append("<empty-block/>")
                elif IMG_RE.match(plain):  # 在 Notion 手動寫的 [圖:檔名] 仍然有效
                    self.lines.append(plain)
                else:
                    self.lines.append(guard(txt))
            elif t in ("heading_1", "heading_2", "heading_3"):
                if plain:
                    self.lines.append("#" * int(t[-1]) + " " + txt)
            elif t == "bulleted_list_item":
                if plain:
                    self.lines.append("- " + txt)
            elif t == "numbered_list_item":
                if plain:
                    self.lines.append("1. " + txt)
            elif t == "to_do":
                if plain:
                    self.lines.append("- " + ("☑ " if d.get("checked") else "☐ ") + txt)
            elif t == "quote":
                if plain:
                    self.lines.append("> " + txt)
            elif t == "callout":
                icon = d.get("icon") or {}
                pre = icon.get("emoji", "") + " " if icon.get("type") == "emoji" else ""
                if plain:
                    self.lines.append(guard(pre + txt))
            elif t == "toggle":
                if plain:
                    self.lines.append(guard(txt))
            elif t == "divider":
                self.lines.append("---")
            elif t == "code":
                for ln in "".join(r.get("plain_text", "") for r in rich).split("\n"):
                    ln = ln.rstrip()
                    if ln.strip():
                        self.lines.append(f"`{ln}`" if "`" not in ln else guard(esc_text(ln)))
                self.note("程式碼區塊已轉成逐行文字")
            elif t == "image":
                self.image(d)
            elif t in ("video", "file", "pdf", "audio"):
                ext = (d.get("external") or {}).get("url") if d.get("type") == "external" else None
                if ext and link_ok(ext):
                    self.lines.append(f"[{esc_text(ext)}]({safe_url(ext)})")
                else:
                    self.media += 1
                    self.note(f"{t} 檔案無法搬運，已略過")
            elif t in ("bookmark", "embed", "link_preview"):
                u = d.get("url")
                if u and link_ok(u):
                    self.lines.append(f"[{esc_text(u)}]({safe_url(u)})")
            elif t == "table":
                for row in list_children(b["id"]):
                    cells = (row.get("table_row") or {}).get("cells") or []
                    line = " ｜ ".join(rt_md(c) for c in cells)
                    if line.strip(" ｜"):
                        self.lines.append(guard(line))
                self.note("表格已轉成文字列")
            elif t in ("column_list", "column", "synced_block"):
                pass
            elif t in SKIP_TYPES:
                self.note(f"{t} 區塊已略過")
            else:
                self.note(f"不支援的區塊 {t}，已略過")
            if b.get("has_children") and t not in ("table", "child_page", "child_database"):
                src = b["id"]
                if t == "synced_block" and d.get("synced_from"):
                    src = d["synced_from"]["block_id"]
                self.walk(list_children(src))

    def image(self, d):
        self.media += 1
        src = (d.get("file") or {}).get("url") if d.get("type") == "file" else (d.get("external") or {}).get("url")
        cap = re.sub(r"[\]|｜\r\n]+", " ", "".join(r.get("plain_text", "") for r in d.get("caption") or [])).strip()
        if not src:
            self.note("有一張圖片找不到網址，已略過")
            return
        try:
            name = save_image(self.prefix, src, self.img_dir)
        except Exception as e:  # 單張圖片失敗不要中斷整篇
            self.note(f"有一張圖片處理失敗（{e if isinstance(e, SyncError) else type(e).__name__}），已略過")
            return
        self.used.add(name)
        self.lines.append(f"[圖:{name}|{cap}]" if cap else f"[圖:{name}]")

    def result(self):
        lines = list(self.lines)
        while lines and lines[0] == "<empty-block/>":
            lines.pop(0)
        while lines and lines[-1] == "<empty-block/>":
            lines.pop()
        return "\n".join(lines)


def convert_page(page, post_id, img_dir=None):
    c = Conv(post_id, img_dir)
    c.walk(list_children(page["id"]))
    return c


def cleanup_orphans(post_id, used):
    """只清自己產生的 p{id}-xxxx 檔，手動上傳的圖片不會被動到。"""
    removed = []
    if IMG_DIR.exists():
        for f in IMG_DIR.glob(f"p{post_id}-*"):
            if f.name not in used:
                f.unlink()
                removed.append(f.name)
    return removed


# ───────────────────────── 作品 ─────────────────────────

MANAGED_IMG_RE = re.compile(r"^(?:w-[a-z0-9\-]+|p\d+)-[0-9a-f]{8}\.[A-Za-z0-9]+$")  # 腳本產生的圖檔；其餘視為手動上傳


def md_images(md):
    out = []
    for ln in md.split("\n"):
        m = IMG_RE.match(ln.strip())
        if m:
            out.append(m.group(1))
    return out


def dump_works(works):
    return json.dumps(works, ensure_ascii=False, indent=1) + "\n"


def https_link(u):
    return u if u and u.lower().startswith("https://") and link_ok(u) else ""


def sync_works(force):
    """以 Notion「作品」資料庫為準，整批重建 works.json。回傳 (新增, 更新, 下架, 問題, 提醒, 掃描筆數)。"""
    added, updated, removed, problems, notices = [], [], [], [], []
    raw = WORKS_PATH.read_text(encoding="utf8") if WORKS_PATH.exists() else "[]\n"
    old = json.loads(raw)
    prev = {w["notion"]: w for w in old if w.get("notion")}
    try:
        pages = all_pages(WORKS_DATA_SOURCE)
    except SyncError as e:
        problems.append(f"作品資料庫讀取失敗，網站上的作品維持原樣：{e}（請確認已在 Notion「作品」資料庫的 ⋯ → 連線 加入這個整合）")
        return added, updated, removed, problems, notices, 0
    if not pages and old:
        problems.append("作品資料庫查到 0 筆，但網站上已有作品；為免誤刪，作品維持原樣。要全部下架請先把網站顯示改成草稿")
        return added, updated, removed, problems, notices, 0

    works, used, slugs = [], set(), set()
    live = [p for p in pages if prop_select(p, W_SHOW) in (S_PUBLISH, S_LIVE)]
    live.sort(key=lambda p: (prop_number(p, W_ORDER) if prop_number(p, W_ORDER) is not None else 9999, prop_title(p, W_TITLE)))
    for page in live:
        title = prop_title(page, W_TITLE)
        label = title or page["id"]
        slug = prop_text(page, W_SLUG)
        old_w = prev.get(page["id"])

        def keep_old(why):
            problems.append(f"「{label}」{why}")
            if old_w and old_w["slug"] not in slugs:
                works.append(old_w)
                slugs.add(old_w["slug"])
                used.update(md_images(old_w["md"]))

        if not title:
            problems.append(f"有一個作品沒有名稱，已略過（{page['id']}）")
            continue
        if not SLUG_RE.match(slug) or slug in RESERVED_SLUGS:
            keep_old(f"的「網址代稱」不合格（只能用英文小寫、數字、連字號，不能是 index 或 img），已略過")
            continue
        if slug in slugs:
            problems.append(f"「{label}」的網址代稱「{slug}」重複，已略過")
            continue
        summary = prop_text(page, W_SUMMARY)
        if not summary:
            keep_old("沒有填「一句話說明」，已略過")
            continue
        edited = page.get("last_edited_time", "")
        unchanged = (old_w and old_w.get("notion_edited") == edited and old_w["slug"] == slug and force != "all"
                     and (not isinstance(force, set) or slug not in force))
        if unchanged:
            w = old_w
            used.update(md_images(w["md"]))
        else:
            try:
                conv = convert_page(page, "w-" + slug, WORKS_IMG_DIR)
            except SyncError as e:
                keep_old(f"讀取失敗：{e}")
                continue
            md = conv.result()
            if not md:
                keep_old("內容是空的，已略過")
                continue
            for name in md_images(md):  # 在 Notion 手寫的 [圖:檔名]：作品頁自己留一份，不依賴部落格的圖檔
                dst = WORKS_IMG_DIR / name
                src = IMG_DIR / name
                if not dst.exists() and src.exists():
                    WORKS_IMG_DIR.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                if not dst.exists():
                    conv.note(f"找不到圖檔 {name}（portfolio/img 與 blog/img 都沒有）")
                conv.used.add(name)
            used.update(conv.used)
            for n in conv.notices:
                notices.append(f"作品「{label}」：{n}")
            w = {"slug": slug, "title": title, "summary": summary,
                 "progress": prop_select(page, W_PROGRESS) or "",
                 "tags": prop_multi(page, W_TAGS), "order": prop_number(page, W_ORDER),
                 "live": https_link(prop_url(page, W_LIVE)), "github": https_link(prop_url(page, W_GITHUB)),
                 "related": prop_relation_ids(page, W_RELATED), "md": md,
                 "notion": page["id"], "notion_edited": edited}
            print(f"作品：{title}（{slug}，圖片 {len(md_images(md))} 張）")
        works.append(w)
        slugs.add(slug)
        if not old_w:
            added.append(title)
        elif not unchanged and any(old_w.get(k) != w.get(k) for k in w if k != "notion_edited"):
            updated.append(title)
    kept = {w["notion"] for w in works}
    removed = [o["title"] for o in old if o.get("notion") not in kept]

    new_text = dump_works(works)
    if new_text != raw:
        WORKS_PATH.write_text(new_text, encoding="utf8")
    if WORKS_IMG_DIR.exists():  # 只清腳本自己產生、而且已不被任何上線作品使用的圖
        for f in WORKS_IMG_DIR.iterdir():
            if f.is_file() and MANAGED_IMG_RE.match(f.name) and f.name not in used:
                f.unlink()
    return added, updated, removed, problems, notices, len(pages)


# ───────────────────────── 主流程 ─────────────────────────

def dump_posts(posts):
    return json.dumps(posts, ensure_ascii=False, indent=1) + "\n"


def parse_resync():
    raw = os.environ.get("RESYNC", "").strip()
    if raw.lower() == "all":
        return "all"
    return {x.strip() for x in raw.replace("，", ",").split(",") if x.strip()}


def main():
    raw_posts = POSTS_PATH.read_text(encoding="utf8")
    posts = json.loads(raw_posts)
    cfg = json.loads(CFG_PATH.read_text(encoding="utf8"))
    categories = {c for z in cfg.get("zones", []) for c in z["categories"]}
    by_notion = {p["notion"]: p for p in posts if p.get("notion")}
    by_id = {str(p["id"]): p for p in posts}
    force = parse_resync()

    pages = all_pages()
    if not pages:
        raise SyncError("查詢到 0 筆資料。請確認已在 Notion「部落格文章」資料庫的 ⋯ → 連線 加入這個整合。")

    added, updated, problems, baselined, notices = [], [], [], [], []
    todo = []
    seen = set()
    for page in pages:
        pid = page["id"]
        seen.add(pid)
        status = prop_select(page, P_STATUS)
        known = by_notion.get(pid)
        if known:
            if status not in (S_PUBLISH, S_LIVE):
                continue
            edited = page.get("last_edited_time", "")
            if not known.get("notion_edited"):
                known["notion_edited"] = edited  # 第一次：只記下基準，不動內容
                baselined.append(known["title"])
            forced = force == "all" or str(known["id"]) in force
            if forced or (edited and edited > known["notion_edited"]):
                todo.append((page, known))
        elif status == S_PUBLISH:
            todo.append((page, None))

    if isinstance(force, set):
        for fid in sorted(force):
            p = by_id.get(fid)
            if p is None:
                problems.append(f"RESYNC 指定的 id {fid} 不存在")
            elif not p.get("notion"):
                problems.append(f"文章 {p['title']}（id {fid}）沒有 Notion 連結，無法重新同步")
            elif p["notion"] not in seen:
                problems.append(f"文章 {p['title']}（id {fid}）在 Notion 找不到對應頁面（是否沒分享給整合？）")

    # 新文章依發布日期排序後編號，結果固定
    todo.sort(key=lambda x: (prop_date(x[0], P_DATE) or "", x[0].get("created_time", "")))
    next_id = max([p["id"] for p in posts] + [0]) + 1

    for page, known in todo:
        title = prop_title(page) or (known or {}).get("title", "")
        category = prop_select(page, P_CATEGORY) or (known or {}).get("category")
        date = prop_date(page, P_DATE) or (known or {}).get("date")
        label = title or page["id"]
        if not title:
            problems.append(f"有一頁沒有標題，已略過（{page['id']}）")
            continue
        if category not in categories:
            problems.append(f"「{label}」的分類「{category}」不在任何專區，已略過（請先設定分類）")
            continue
        if not date:
            problems.append(f"「{label}」沒有發布日期，已略過")
            continue
        post_id = known["id"] if known else next_id
        try:
            conv = convert_page(page, post_id)
        except SyncError as e:
            problems.append(f"「{label}」讀取失敗：{e}")
            continue
        md = conv.result()
        if not md:
            problems.append(f"「{label}」內容是空的，已略過")
            continue
        entry = {"id": post_id, "title": title, "date": date, "category": category,
                 "media": conv.media, "md": md, "notion": page["id"],
                 "notion_edited": page.get("last_edited_time", "")}
        if known:
            changed = any(known.get(k) != entry[k] for k in ("title", "date", "category", "media", "md"))
            known.clear()
            known.update(entry)
            removed = cleanup_orphans(post_id, conv.used)
            if changed or removed:
                updated.append(title)
        else:
            posts.append(entry)
            next_id += 1
            added.append(title)
        for n in conv.notices:
            notices.append(f"「{label}」：{n}")
        imgs = sorted(conv.used)
        print(f"{'更新' if known else '新增'}：{title}（id {post_id}，圖片 {len(imgs)} 張{'：' + '、'.join(imgs) if imgs else ''}）")

    new_text = dump_posts(posts)
    if new_text != raw_posts:
        POSTS_PATH.write_text(new_text, encoding="utf8")

    w_added, w_updated, w_removed, w_problems, w_notices, w_pages = sync_works(force)
    write_summary(added, updated, problems, baselined, notices, len(pages),
                  (w_added, w_updated, w_removed, w_problems, w_notices, w_pages))
    return 1 if any("讀取失敗" in p for p in problems + w_problems) else 0


def write_summary(added, updated, problems, baselined, notices, n_pages, works=None):
    L = ["## Notion 同步結果", "", f"- 掃描 Notion 頁面：{n_pages} 筆",
         f"- 新增文章：{len(added)} 篇", f"- 更新文章：{len(updated)} 篇"]
    for title, items in (("新增", added), ("更新", updated)):
        for t in items:
            L.append(f"  - {title}：{t}")
    if baselined:
        L += ["", f"已替 {len(baselined)} 篇既有文章記下 Notion 編輯時間基準（內容沒有變動）。之後它們在 Notion 被編輯才會自動更新。"]
    if notices:
        L += ["", "### 提醒"] + [f"- {n}" for n in notices]
    if problems:
        L += ["", "### 需要處理"] + [f"- {p}" for p in problems]
    if works:
        wa, wu, wr, wp, wn, wpages = works
        L += ["", "### 作品", "", f"- 掃描作品頁面：{wpages} 筆",
              f"- 新增作品：{len(wa)} 個", f"- 更新作品：{len(wu)} 個", f"- 下架作品：{len(wr)} 個"]
        for tag, items in (("新增", wa), ("更新", wu), ("下架", wr)):
            L += [f"  - {tag}：{t}" for t in items]
        if wn:
            L += ["", "作品提醒："] + [f"- {n}" for n in wn]
        if wp:
            L += ["", "作品需要處理："] + [f"- {p}" for p in wp]
        if not (wa or wu or wr or wp):
            L += ["", "作品沒有變動。"]
    if not (added or updated or problems) and not works:
        L += ["", "沒有需要同步的新內容。"]
    text = "\n".join(L) + "\n"
    print("\n" + text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf8") as f:
            f.write(text)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SyncError as e:
        print(f"同步失敗：{e}", file=sys.stderr)
        path = os.environ.get("GITHUB_STEP_SUMMARY")
        if path:
            with open(path, "a", encoding="utf8") as f:
                f.write(f"## Notion 同步失敗\n\n{e}\n")
        sys.exit(1)
