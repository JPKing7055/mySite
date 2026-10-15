#!/usr/bin/env python3
"""離線測試 sync_notion.py：用假的 Notion 資料，不連網、不動真正的 posts.json 與 blog/。

執行：  pip install pillow markdown-it-py   &&   python3 tools/test_sync_notion.py
"""
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="synctest-"))
(TMP / "tools").mkdir()
for f in ("posts.json", "blog_config.json", "build_blog.py", "build_works.py", "sync_notion.py"):
    shutil.copy(REPO / "tools" / f, TMP / "tools" / f)
(TMP / "blog").mkdir()
shutil.copytree(REPO / "blog" / "img", TMP / "blog" / "img")  # 真實文章引用的圖，建置時才不會有 WARNING
# 測試要從「還沒記下 Notion 編輯時間基準」開始，不要受真實資料已同步過的影響
_posts = json.loads((TMP / "tools" / "posts.json").read_text(encoding="utf8"))
for _p in _posts:
    _p.pop("notion_edited", None)
(TMP / "tools" / "posts.json").write_text(json.dumps(_posts, ensure_ascii=False, indent=1) + "\n", encoding="utf8")
(TMP / "portfolio").mkdir()
shutil.copy(REPO / "portfolio" / "index.html", TMP / "portfolio" / "index.html")

os.environ["SYNC_ROOT"] = str(TMP)
os.environ["NOTION_TOKEN"] = "test-token-not-real"
sys.path.insert(0, str(TMP / "tools"))
sn = importlib.import_module("sync_notion")


# ───────── 假資料工具 ─────────
def rt(text, **ann):
    href = ann.pop("href", None)
    return {"type": "text", "plain_text": text, "href": href, "annotations": ann}


def block(i, t, rich=None, children=False, **extra):
    d = {"rich_text": rich or []}
    d.update(extra)
    return {"id": i, "type": t, "has_children": children, t: d}


def page(pid, title, status, cat="AI創作", date="2026-10-13", edited="2026-10-13T01:00:00.000Z"):
    return {"id": pid, "created_time": "2026-10-12T00:00:00.000Z", "last_edited_time": edited,
            "properties": {
                "標題": {"title": [{"plain_text": title}]},
                "分類": {"select": {"name": cat} if cat else None},
                "狀態": {"select": {"name": status} if status else None},
                "發布日期": {"date": {"start": date} if date else None}}}


def jpeg_with_exif(w, h):
    im = Image.new("RGB", (w, h), (200, 120, 60))
    ex = Image.Exif()
    ex[0x010F] = "TESTCAM"
    gps = ex.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (25.0, 2.0, 3.0), "E", (121.0, 30.0, 0.0)
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=ex)
    return buf.getvalue()


def png_alpha():
    buf = io.BytesIO()
    Image.new("RGBA", (50, 40), (255, 0, 0, 100)).save(buf, "PNG")
    return buf.getvalue()


def gif_anim():
    buf = io.BytesIO()
    frames = [Image.new("RGB", (20, 20), c).convert("P") for c in ((255, 0, 0), (0, 0, 255))]
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    return buf.getvalue()


URL_JPG = "https://prod-files-secure.example/ws/abc-111/photo.jpg?X-Sig=AAA"
URL_JPG_SAME_FILE_NEW_SIG = "https://prod-files-secure.example/ws/abc-111/photo.jpg?X-Sig=BBB"
URL_JPG2 = "https://prod-files-secure.example/ws/abc-222/other.jpg?X-Sig=CCC"
URL_PNG = "https://img.example.com/logo.png"
URL_GIF = "https://prod-files-secure.example/ws/abc-333/anim.gif?X-Sig=DDD"
BYTES = {URL_JPG: jpeg_with_exif(3000, 2000), URL_JPG_SAME_FILE_NEW_SIG: jpeg_with_exif(3000, 2000),
         URL_JPG2: jpeg_with_exif(800, 600), URL_PNG: png_alpha(), URL_GIF: gif_anim()}


class Fake:
    def __init__(self):
        self.pages, self.children, self.downloads = [], {}, []
        self.works_pages, self.works_error = [], False
        self.now_page, self.now_error = None, False

    def notion(self, method, path, body=None):
        if method == "POST" and "/query" in path and sn.WORKS_DATA_SOURCE in path:
            if self.works_error:
                raise sn.SyncError("Notion API 回應 404（POST /data_sources/x/query）")
            return {"results": self.works_pages, "has_more": False}
        if method == "POST" and "/query" in path:
            first, rest = self.pages[:2], self.pages[2:]  # 測試分頁
            if (body or {}).get("start_cursor"):
                return {"results": rest, "has_more": False}
            return {"results": first, "has_more": bool(rest), "next_cursor": "c2"}
        if method == "GET" and path.startswith("/pages/"):
            if self.now_error:
                raise sn.SyncError("Notion API 回應 404（GET /pages/x）")
            return self.now_page
        if method == "GET" and path.startswith("/blocks/"):
            bid = path.split("/")[2]
            return {"results": self.children.get(bid, []), "has_more": False}
        raise AssertionError(f"unexpected call {method} {path}")

    def http_get(self, url):
        self.downloads.append(url)
        if url not in BYTES:
            raise sn.SyncError("下載失敗 HTTP 403")
        return BYTES[url]


fake = Fake()
sn.notion = fake.notion
sn.http_get = fake.http_get

A = "aaaaaaaa-0000-0000-0000-000000000001"
SYN = "aaaaaaaa-0000-0000-0000-0000000000s1"
a_blocks = [
    block("b1", "heading_1", [rt("標題一")]),
    block("b2", "paragraph", [rt("你好 "), rt("粗體(含符號)", bold=True), rt("，連結", ), rt("官網", href="https://example.com/a b)"),
                              rt(" 與 "), rt("code_x", code=True), rt("\n換行*星號*_底線_")]),
    block("b3", "paragraph", []),
    block("b4", "bulleted_list_item", [rt("項目一")], children=True),
    block("b5", "numbered_list_item", [rt("第一步")]),
    block("b6", "to_do", [rt("待辦")], checked=True),
    block("b7", "quote", [rt("引言")]),
    block("b8", "callout", [rt("提醒")], icon={"type": "emoji", "emoji": "💡"}),
    block("b9", "divider"),
    block("b10", "image", type="file", file={"url": URL_JPG}, caption=[rt("圖說含]與|符號")]),
    block("b11", "image", type="external", external={"url": URL_PNG}, caption=[]),
    block("b12", "image", type="file", file={"url": URL_GIF}, caption=[]),
    block("b13", "image", type="file", file={"url": "https://prod-files-secure.example/ws/zzz/missing.jpg?X-Sig=EEE"}, caption=[]),
    block("b14", "bookmark", url="https://example.org/page_1"),
    block("b15", "video", type="external", external={"url": "https://youtu.be/xyz"}),
    block("b16", "file", type="file", file={"url": "https://x/y.zip"}),
    block("b17", "table", children=True),
    block("b18", "code", [rt("print('a')\nprint(`b`)")]),
    block("b19", "column_list", children=True),
    block("b20", "synced_block", children=True, synced_from={"block_id": SYN}),
    block("b21", "child_page", title="私人子頁"),
    block("b22", "paragraph", [rt("- 假清單")]),
    block("b23", "paragraph", [rt("1. 假編號")]),
    block("b24", "paragraph", [rt("# 假標題")]),
    block("b25", "paragraph", [rt("[圖:manual.png|手動]")]),
    block("b26", "paragraph", [rt("<b>不是標籤</b> & 符號")]),
    block("b27", "paragraph", []),
]
fake.children[A] = a_blocks
fake.children["b4"] = [block("b4c", "bulleted_list_item", [rt("子項目")])]
fake.children["b17"] = [{"id": "r1", "type": "table_row", "has_children": False, "table_row": {"cells": [[rt("甲")], [rt("乙")]]}}]
fake.children["b19"] = [block("col", "column", children=True)]
fake.children["col"] = [block("cp", "paragraph", [rt("欄內文字")])]
fake.children[SYN] = [block("sp", "paragraph", [rt("同步區塊文字")])]

# 「現在在做的事」頁面：內文放在同步區塊裡（跟真實頁面一樣），標題是 heading_4、第二行是粗體
NOW_ID = sn.NOW_PAGE
fake.now_page = {"id": NOW_ID, "last_edited_time": "2026-10-15T05:59:00.083Z"}
fake.children[NOW_ID] = [
    {**block("nsb", "synced_block", children=True, synced_from=None), "last_edited_time": "2026-10-15T05:59:00.000Z"},
    block("nes", "paragraph", []),
]
fake.children["nsb"] = [
    block("nh", "heading_4", [rt("簡報結束啦，專案概念呈現太醜又太難聽被嫌了wwww")]),
    block("np", "paragraph", [rt("接下來就是團專跟個人專頁的整理", bold=True)]),
]

posts0 = json.loads((TMP / "tools/posts.json").read_text(encoding="utf8"))
NEW_ID = max(p["id"] for p in posts0) + 1  # 新文章會拿到的 id（隨網站文章增加）
p706 = next(p for p in posts0 if p["id"] == 706)
p701 = next(p for p in posts0 if p["id"] == 701)
p687 = next(p for p in posts0 if p["id"] == 687)  # 舊文，沒有 notion 欄位
fake.pages = [
    page(A, "測試新文章", "待發布"),
    page("bbbbbbbb-0000-0000-0000-000000000002", "只留在 Notion 的舊文", "已發布", cat="未分類", date="2008-01-01"),
    page("cccccccc-0000-0000-0000-000000000003", "分類不存在", "待發布", cat="不存在的分類"),
    page("dddddddd-0000-0000-0000-000000000004", "沒有日期", "待發布", date=None),
    page(p706["notion"], p706["title"], "已發布", edited="2026-10-12T02:00:00.000Z"),
    page(p701["notion"], p701["title"], "寫作中", edited="2026-10-12T02:00:00.000Z"),
    page("eeeeeeee-0000-0000-0000-000000000005", "草稿", "寫作中"),
]
fake.children[p706["notion"]] = [block("p6a", "paragraph", [rt("706 新內容")]),
                                 block("p6i", "image", type="file", file={"url": URL_JPG2}, caption=[rt("人際網圖")])]


def run(resync=""):
    os.environ["RESYNC"] = resync
    importlib.reload(sn)
    sn.notion, sn.http_get = fake.notion, fake.http_get
    code = sn.main()
    return code, json.loads((TMP / "tools/posts.json").read_text(encoding="utf8"))


def check(cond, msg):
    print(("  OK  " if cond else "  FAIL ") + msg)
    if not cond:
        check.failed += 1


check.failed = 0

# ───────── 第 1 次：新增 ─────────
print("== run 1")
code, posts = run()
new = [p for p in posts if p["id"] == NEW_ID]
check(code == 0, "exit code 0")
check(len(posts) == len(posts0) + 1 and len(new) == 1, "只新增 1 篇（id NEW_ID）")
e = new[0]
md = e["md"]
print(md)
check("只留在 Notion" not in json.dumps(posts, ensure_ascii=False), "已發布的舊文沒被加進來")
check(not any(p["title"] in ("分類不存在", "沒有日期", "草稿") for p in posts), "分類不存在／沒日期／草稿都沒被加進來")
check(e["notion"] == A and e["notion_edited"].startswith("2026-10-13"), "記下 notion 與 notion_edited")
check("# 標題一" in md.split("\n")[0], "heading_1 → # ")
check("<strong>粗體(含符號)</strong>" in md, "粗體用 <strong>")
check("[官網](https://example.com/a%20b%29)" in md, "連結網址已處理空格與括號")
check("`code_x`" in md and "<br>換行\\*星號\\*\\_底線\\_" in md, "行內程式碼、換行、特殊符號跳脫")
check("\n<empty-block/>\n" in md, "空段落 → <empty-block/>")
check("- 項目一\n- 子項目" in md, "子項目攤平成同層清單")
check("- ☑ 待辦" in md and "> 引言" in md and "💡 提醒" in md and "\n---\n" in md, "to_do／quote／callout／divider")
check(f"[圖:p{NEW_ID}-" in md and "|圖說含 與 符號]" in md, "圖說的 ] 與 | 被清掉")
imgs = sorted((TMP / "blog/img").glob(f"p{NEW_ID}-*"))
names = [f.name for f in imgs]
check(len(imgs) == 3, f"產生 3 個圖檔（jpg、png、gif）：{names}")
jpg = next(f for f in imgs if f.suffix == ".jpg")
im = Image.open(jpg)
check(im.width == 1600, "jpg 縮到 1600px 寬")
check(len(im.getexif()) == 0, "jpg 已移除 EXIF（含 GPS）")
check(jpg.stat().st_size <= 1024 * 1024, "jpg ≤ 1MB")
png = next(f for f in imgs if f.suffix == ".png")
check(Image.open(png).mode == "RGBA", "有透明度的 png 保留 png")
gif = next(f for f in imgs if f.suffix == ".gif")
check(gif.read_bytes() == BYTES[URL_GIF], "動態 gif 保留原檔")
check(e["media"] == 5, f"media 計數（4 張圖含 1 張下載失敗＋1 個無法搬運的檔案）＝ {e['media']}，預期 5")
check("[YouTube]" not in md and "https://youtu.be/xyz" in md.replace("\\_", "_"), "外部影片以連結呈現")
check("甲 ｜ 乙" in md and "欄內文字" in md and "同步區塊文字" in md, "表格、欄、同步區塊")
check("私人子頁" not in md, "child_page 不輸出")
check("\\- 假清單" in md and "1\\. 假編號" in md and "\\# 假標題" in md, "一般文字不會被誤認成清單／標題")
check("\n[圖:manual.png|手動]\n" in md, "手動 [圖:...] 標記保留")
check("\\<b\\>不是標籤\\</b\\> & 符號" in md, "文字裡的 < > 被跳脫")
check(next(p for p in posts if p["id"] == 706).get("notion_edited") == "2026-10-12T02:00:00.000Z"
      and next(p for p in posts if p["id"] == 706)["md"] == p706["md"], "706：只記下基準，內容不動")
check(next(p for p in posts if p["id"] == 701)["md"] == p701["md"] and "notion_edited" not in next(p for p in posts if p["id"] == 701), "狀態是寫作中的 701 完全沒被動")
check(next(p for p in posts if p["id"] == 687) == p687, "沒有 notion 欄位的舊文完全沒被動")
check(all(" X-Sig" not in l and "X-Sig" not in l for l in md.split("\n")), "文章內容沒有簽名網址")
dl1 = list(fake.downloads)

# ───────── 第 2 次：沒變動 → 什麼都不做 ─────────
print("== run 2 (idempotent)")
before = (TMP / "tools/posts.json").read_bytes()
fake.downloads.clear()
code, posts = run()
check((TMP / "tools/posts.json").read_bytes() == before, "posts.json 逐位元相同")
check(not fake.downloads, "沒有重新下載圖片")

# ───────── 第 3 次：Notion 編輯 → 更新並清掉不用的圖 ─────────
print("== run 3 (edited in Notion)")
fake.pages[0] = page(A, "測試新文章（改標題）", "已發布", edited="2026-10-13T05:00:00.000Z")
fake.children[A] = [block("n1", "paragraph", [rt("改過的內文")]),
                    block("n2", "image", type="file", file={"url": URL_JPG_SAME_FILE_NEW_SIG}, caption=[])]
fake.downloads.clear()
code, posts = run()
e = next(p for p in posts if p["id"] == NEW_ID)
left = sorted(f.name for f in (TMP / "blog/img").glob(f"p{NEW_ID}-*"))
check(e["title"] == "測試新文章（改標題）" and e["md"].startswith("改過的內文"), "標題與內文已更新")
check(len(left) == 1 and left[0] in e["md"], f"同一張圖換了簽名網址：沿用同檔名，其餘舊圖已清掉：{left}")
check(not fake.downloads, "同一張圖（簽名不同）沒有重新下載")
check(e["id"] == NEW_ID and len(posts) == len(posts0) + 1, "id 不變、沒有重複新增")

# ───────── 第 4 次：RESYNC 強制 ─────────
print("== run 4 (RESYNC=706)")
code, posts = run("706")
q = next(p for p in posts if p["id"] == 706)
check(q["md"].startswith("706 新內容") and "|人際網圖]" in q["md"] and q["media"] == 1, "706 已重新同步並放入圖片")
check(any(f.name.startswith("p706-") for f in (TMP / "blog/img").iterdir()), "p706 圖檔存在")
code, posts = run("999")
check(code == 0, "指定不存在的 id 只提醒，不會當掉")

# ───────── 建置 ─────────
print("== build")
r = subprocess.run([sys.executable, "-I", str(TMP / "tools/build_blog.py")], capture_output=True, text=True, cwd=TMP)
print(r.stdout.strip(), r.stderr.strip()[:300])
check(r.returncode == 0 and "WARNING" not in r.stdout, "建置成功、沒有 WARNING（沒有找不到的圖）")
html = (TMP / f"blog/posts/{NEW_ID}.html").read_text(encoding="utf8")
check(f'<figure><img src="../img/p{NEW_ID}-' in html, "文章頁有 <figure><img>")
check(0 < html.count("<figure>") and "&lt;strong&gt;" not in html, "文章頁沒有把標籤當文字")
alltxt = (TMP / "blog/all.html").read_text(encoding="utf8")
check("&lt;strong&gt;" not in alltxt and "&lt;br&gt;" not in alltxt, "列表摘要沒有露出 HTML 標籤")

# ───────────────────────── 作品 ─────────────────────────
print("== works")


def wpage(pid, title, show, slug, summary="一句話說明", progress="開發中", order=1, tags=(), related=(),
          live="", github="", edited="2026-10-13T01:00:00.000Z"):
    return {"id": pid, "last_edited_time": edited, "properties": {
        "作品名稱": {"title": [{"plain_text": title}]},
        "一句話說明": {"rich_text": [{"plain_text": summary}] if summary else []},
        "專案進度": {"select": {"name": progress} if progress else None},
        "網站顯示": {"select": {"name": show} if show else None},
        "網址代稱": {"rich_text": [{"plain_text": slug}] if slug else []},
        "技術與工具": {"multi_select": [{"name": t} for t in tags]},
        "顯示順序": {"number": order},
        "成品連結": {"url": live or None}, "GitHub 連結": {"url": github or None},
        "相關文章": {"relation": [{"id": r} for r in related]}}}


def wrun(resync=""):
    code, _ = run(resync)
    return code, json.loads((TMP / "tools/works.json").read_text(encoding="utf8")) if (TMP / "tools/works.json").exists() else None


(TMP / "blog/img").mkdir(parents=True, exist_ok=True)
if not (TMP / "blog/img/p705-f40730aa.png").exists():
    Image.new("RGB", (30, 20), (1, 2, 3)).save(TMP / "blog/img/p705-f40730aa.png")  # 部落格已有的圖
(TMP / "portfolio/img").mkdir(parents=True, exist_ok=True)
(TMP / "portfolio/img/hand-made.png").write_bytes(b"manual")  # 手動上傳的圖（不是腳本產生的檔名）
(TMP / "portfolio/img/w-old-work-deadbeef.png").write_bytes(b"orphan")  # 腳本產生、但已不被使用的舊圖

W1, W2, W3, W4, W5, W6 = (f"wwwwwwww-0000-0000-0000-00000000000{i}" for i in range(1, 7))
fake.children[W1] = [block("w1a", "heading_2", [rt("專案簡介")]), block("w1b", "paragraph", [rt("第一個作品")]),
                     block("w1c", "image", type="file", file={"url": URL_JPG2}, caption=[rt("原型畫面")]),
                     block("w1d", "paragraph", [rt("[圖:p705-f40730aa.png|手寫圖說]")]),
                     block("w1e", "paragraph", [rt("[圖:nowhere.png]")])]
fake.children[W2] = [block("w2a", "paragraph", [rt("第二個作品")])]
fake.children[W3] = [block("w3a", "paragraph", [rt("草稿不會上網")])]
for w in (W4, W5, W6):
    fake.children[w] = [block(w + "a", "paragraph", [rt("不該上網")])]
p705 = next(p for p in posts0 if p["id"] == 705)
fake.works_pages = [
    wpage(W2, "作品二", "已發布", "second-work", order=2, tags=["Gemini", "LINE Bot"], live="https://example.com/app", github="javascript:alert(1)"),
    wpage(W1, "作品一", "待發布", "first-work", order=1, progress="測試中", related=[p705["notion"], "ffffffff-0000-0000-0000-00000000dead"]),
    wpage(W3, "草稿作品", "草稿", "draft-work"),
    wpage(W4, "代稱有問題", "待發布", "Bad Slug!"),
    wpage(W5, "沒有說明", "待發布", "no-summary", summary=""),
    wpage(W6, "保留字", "待發布", "index"),
]
code, works = wrun()
check(code == 0, "exit code 0")
check([w["slug"] for w in works] == ["first-work", "second-work"], f"只有待發布／已發布的合格作品，依顯示順序排列：{[w['slug'] for w in (works or [])]}")
w1, w2 = works
check(w1["progress"] == "測試中" and w2["tags"] == ["Gemini", "LINE Bot"], "專案進度與標籤")
check(w2["live"] == "https://example.com/app" and w2["github"] == "", "成品連結保留 https；javascript: 這類網址被丟掉")
check(w1["notion"] == W1 and w1["notion_edited"].startswith("2026-10-13"), "記下 notion 與 notion_edited")
wimgs = sorted(f.name for f in (TMP / "portfolio/img").iterdir())
check(any(n.startswith("w-first-work-") for n in wimgs), f"Notion 圖片區塊存進 portfolio/img（w-slug 前綴）：{wimgs}")
check("p705-f40730aa.png" in wimgs, "手寫的 [圖:p705-...] 會從 blog/img 複製一份到 portfolio/img")
check("hand-made.png" in wimgs, "手動上傳的圖不會被清掉")
check("w-old-work-deadbeef.png" not in wimgs, "腳本產生、已不被使用的舊圖會清掉")
check("|原型畫面]" in w1["md"] and "手寫圖說" in w1["md"], "圖說保留")
check("X-Sig" not in json.dumps(works, ensure_ascii=False), "works.json 沒有簽名網址")

print("== works run 2 (idempotent)")
before = (TMP / "tools/works.json").read_bytes()
fake.downloads.clear()
code, works = wrun()
check((TMP / "tools/works.json").read_bytes() == before, "works.json 逐位元相同")
check(not fake.downloads, "沒有重新下載圖片")

print("== works build")
r = subprocess.run([sys.executable, "-I", str(TMP / "tools/build_works.py")], capture_output=True, text=True, cwd=TMP)
print(r.stdout.strip(), r.stderr.strip()[:400])
check(r.returncode == 0, "build_works 成功")
idx = (TMP / "portfolio/index.html").read_text(encoding="utf8")
check("first-work.html" in idx and "second-work.html" in idx and "作品整理中" not in idx, "首頁有兩張作品卡片、沒有「整理中」")
check(idx.index("作品一") < idx.index("作品二"), "卡片依顯示順序")
check("WORKS:START" in idx and "WORKS:END" in idx, "標記還在（下次可以再重建）")
check('href="https://example.com/app"' in idx and "javascript:" not in idx, "成品連結出現在卡片上")
case = (TMP / "portfolio/first-work.html").read_text(encoding="utf8")
check(case.startswith("<!-- generated by build_works -->"), "案例頁有產生標記")
check('src="img/p705-f40730aa.png"' in case and "<figcaption>手寫圖說</figcaption>" in case, "案例頁圖片用 img/ 相對路徑")
check("WARNING" in r.stdout and "nowhere.png" in r.stdout, "找不到的圖會印 WARNING")
check(f'blog/posts/{p705["id"]}.html' in case and "dead" not in case, "相關文章：只列出網站上有的文章")
check('href="../portfolio/index.html" class="text-sky-600' in case and 'href="../blog/index.html" class="text-slate-600' in case, "導覽列高亮「成員作品」")
check("&lt;" not in case.split('class="post-body')[1].split("</article>")[0], "案例頁沒有把標籤當文字")
(TMP / "portfolio/hand-page.html").write_text("<html>手寫頁</html>", encoding="utf8")

print("== works run 3 (edit / unpublish)")
fake.works_pages[0] = wpage(W2, "作品二（改名）", "已發布", "second-work", order=2, edited="2026-10-13T09:00:00.000Z")
fake.works_pages[1] = wpage(W1, "作品一", "草稿", "first-work", order=1)  # 下架
code, works = wrun()
check([w["slug"] for w in works] == ["second-work"] and works[0]["title"] == "作品二（改名）", "改名已更新、作品一已從 works.json 拿掉")
wimgs = sorted(f.name for f in (TMP / "portfolio/img").iterdir())
check(not any(n.startswith("w-first-work-") for n in wimgs) and "p705-f40730aa.png" not in wimgs, f"下架作品的圖一併清掉：{wimgs}")
check("hand-made.png" in wimgs, "手動上傳的圖仍在")
r = subprocess.run([sys.executable, "-I", str(TMP / "tools/build_works.py")], capture_output=True, text=True, cwd=TMP)
check(not (TMP / "portfolio/first-work.html").exists(), "下架作品的案例頁已刪除")
check((TMP / "portfolio/hand-page.html").exists() and (TMP / "portfolio/index.html").exists(), "手寫的頁面（沒有產生標記）不會被刪")

print("== works run 4 (database unreachable / empty)")
before = (TMP / "tools/works.json").read_bytes()
fake.works_error = True
code, works = wrun()
check(code == 1 and (TMP / "tools/works.json").read_bytes() == before, "作品資料庫讀不到：works.json 維持原樣，並回報失敗讓你看到")
fake.works_error = False
fake.works_pages = []
code, works = wrun()
check((TMP / "tools/works.json").read_bytes() == before, "查到 0 筆但網站已有作品：不會整批清空")

print("== works run 5 (all unpublished)")
fake.works_pages = [wpage(W2, "作品二（改名）", "草稿", "second-work", order=2)]
code, works = wrun()
check(works == [], "全部改成草稿 → 全部下架")
r = subprocess.run([sys.executable, "-I", str(TMP / "tools/build_works.py")], capture_output=True, text=True, cwd=TMP)
idx = (TMP / "portfolio/index.html").read_text(encoding="utf8")
check("作品整理中" in idx and "second-work.html" not in idx, "沒有作品時顯示「作品整理中」")

# ───────────────────────── 現在在做的事 ─────────────────────────
print("== now")


def now_cfg():
    return json.loads((TMP / "tools/blog_config.json").read_text(encoding="utf8"))["now"]


def now_run():
    os.environ["RESYNC"] = ""
    importlib.reload(sn)
    sn.notion, sn.http_get = fake.notion, fake.http_get
    return sn.sync_now()


cfg_before = json.loads((TMP / "tools/blog_config.json").read_text(encoding="utf8"))
n = now_cfg()
check(n["paragraphs"] == ["簡報結束啦，專案概念呈現太醜又太難聽被嫌了wwww", "接下來就是團專跟個人專頁的整理"],
      f"內文（同步區塊裡的 H4＋粗體）已寫進 now：{n['paragraphs']}")
check(n["updated"] == "2026-10-15" and n["title"] == "現在在做的事", f"更新日期用 Notion 最後編輯日（台北時間）：{n['updated']}")
check(json.dumps(cfg_before, ensure_ascii=False, indent=2) + "\n" == (TMP / "tools/blog_config.json").read_text(encoding="utf8"),
      "blog_config.json 格式不變（其他設定沒被動到）")
zones_now = cfg_before["zones"]
check(len(zones_now) == 12 and cfg_before["groups"] == ["工作與創作", "興趣與生活"], "專區與分組設定原封不動")

before = (TMP / "tools/blog_config.json").read_bytes()
res = now_run()
check(res[0] == "沒有變動" and (TMP / "tools/blog_config.json").read_bytes() == before, "內文沒變：設定檔逐位元相同、日期不動")

# 只改了日期相關的編輯時間、文字沒變 → 不動
fake.now_page["last_edited_time"] = "2026-10-20T01:00:00.000Z"
res = now_run()
check(res[0] == "沒有變動" and now_cfg()["updated"] == "2026-10-15", "只是編輯時間變了、文字沒變：日期不更新")

# 外層清掉重打：新內文＋跨日（UTC 16:30 ＝ 台北隔天 00:30）
fake.children["nsb"] = [block("nh2", "heading_2", [rt("開始整理團專")]),
                        block("np2", "bulleted_list_item", [rt("整理個人專頁"), rt("\n第二行", bold=True)], children=True),
                        block("code1", "code", [rt("print('不要')")]),
                        block("emp", "paragraph", [])]
fake.children["np2"] = [{**block("np2c", "paragraph", [rt("子項目")]), "last_edited_time": "2026-10-15T16:30:00.000Z"}]
fake.now_page["last_edited_time"] = "2026-10-15T10:00:00.000Z"
res = now_run()
n = now_cfg()
check(res[0] == "已更新" and n["paragraphs"] == ["開始整理團專", "整理個人專頁 第二行", "子項目"],
      f"新內文：空段落與程式碼略過、換行併成一行、子項目算一段：{n['paragraphs']}")
check(n["updated"] == "2026-10-16", f"取頁面與區塊中最晚的編輯時間，並換算成台北日期：{n['updated']}")

# 外層正在重打：頁面是空的 → 網站維持原樣
fake.children["nsb"] = []
before = (TMP / "tools/blog_config.json").read_bytes()
res = now_run()
check(res[0] is None and res[1] and "空的" in res[1] and "讀取失敗" not in res[1], "內文是空的：只提醒，不當成失敗")
check((TMP / "tools/blog_config.json").read_bytes() == before, "內文是空的：網站上的內容維持原樣")

# 讀不到（整合還沒連線到這個頁面）→ 維持原樣＋回報失敗
fake.now_error = True
res = now_run()
check(res[0] is None and "讀取失敗" in res[1] and "連線" in res[1], "頁面讀不到：訊息說明要加連線")
check((TMP / "tools/blog_config.json").read_bytes() == before, "頁面讀不到：網站上的內容維持原樣")
code, _ = run()
check(code == 1, "頁面讀不到：整個同步回報失敗，讓你看得到")
fake.now_error = False

# 有 Notion API 讀不到的區塊（例如 H4）→ 寧可維持原樣，不要只顯示一半
fake.children["nsb"] = [{"id": "unsup", "type": "unsupported", "has_children": False, "unsupported": {}},
                        block("np4", "paragraph", [rt("只剩這一行")])]
before = (TMP / "tools/blog_config.json").read_bytes()
res = now_run()
check(res[0] is None and "H4" in res[1] and (TMP / "tools/blog_config.json").read_bytes() == before,
      "有讀不到的區塊：網站維持原樣並說明原因")
check("讀取失敗" not in res[1], "讀不到區塊：提醒但不讓整個同步顯示失敗")

# 太多段 → 只取前 8 段並提醒
fake.children["nsb"] = [block(f"m{i}", "paragraph", [rt(f"第{i}段")]) for i in range(1, 12)]
res = now_run()
check(res[0] == "已更新" and len(now_cfg()["paragraphs"]) == 8 and res[2] and "11" in res[2], "超過 8 段只取前 8 段，並提醒")

# 頁面被刪掉
fake.now_page["in_trash"] = True
res = now_run()
check(res[0] is None and "讀取失敗" in res[1], "頁面被刪掉：維持原樣並回報")
fake.now_page["in_trash"] = False

# 建置：首頁大區塊吃新內容
fake.children["nsb"] = [block("nh3", "heading_4", [rt("測試 <b>標題</b>")]), block("np3", "paragraph", [rt("內文")])]
code, _ = run()
r = subprocess.run([sys.executable, "-I", str(TMP / "tools/build_blog.py")], capture_output=True, text=True, cwd=TMP)
home = (TMP / "blog/index.html").read_text(encoding="utf8")
check(r.returncode == 0 and "測試 &lt;b&gt;標題&lt;/b&gt;" in home and "更新於 2026-10-15" in home, "首頁「現在在做的事」顯示新內容（HTML 已跳脫）")

shutil.rmtree(TMP, ignore_errors=True)
print("\n失敗項目：", check.failed)
sys.exit(1 if check.failed else 0)
