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
for f in ("posts.json", "blog_config.json", "build_blog.py", "sync_notion.py"):
    shutil.copy(REPO / "tools" / f, TMP / "tools" / f)
(TMP / "blog").mkdir()

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

    def notion(self, method, path, body=None):
        if method == "POST" and "/query" in path:
            first, rest = self.pages[:2], self.pages[2:]  # 測試分頁
            if (body or {}).get("start_cursor"):
                return {"results": rest, "has_more": False}
            return {"results": first, "has_more": bool(rest), "next_cursor": "c2"}
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

posts0 = json.loads((TMP / "tools/posts.json").read_text(encoding="utf8"))
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
new = [p for p in posts if p["id"] == 707]
check(code == 0, "exit code 0")
check(len(posts) == len(posts0) + 1 and len(new) == 1, "只新增 1 篇（id 707）")
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
check("[圖:p707-" in md and "|圖說含 與 符號]" in md, "圖說的 ] 與 | 被清掉")
imgs = sorted((TMP / "blog/img").glob("p707-*"))
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
e = next(p for p in posts if p["id"] == 707)
left = sorted(f.name for f in (TMP / "blog/img").glob("p707-*"))
check(e["title"] == "測試新文章（改標題）" and e["md"].startswith("改過的內文"), "標題與內文已更新")
check(len(left) == 1 and left[0] in e["md"], f"同一張圖換了簽名網址：沿用同檔名，其餘舊圖已清掉：{left}")
check(not fake.downloads, "同一張圖（簽名不同）沒有重新下載")
check(e["id"] == 707 and len(posts) == len(posts0) + 1, "id 不變、沒有重複新增")

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
html = (TMP / "blog/posts/707.html").read_text(encoding="utf8")
check('<figure><img src="../img/p707-' in html, "文章頁有 <figure><img>")
check(0 < html.count("<figure>") and "&lt;strong&gt;" not in html, "文章頁沒有把標籤當文字")
alltxt = (TMP / "blog/all.html").read_text(encoding="utf8")
check("&lt;strong&gt;" not in alltxt and "&lt;br&gt;" not in alltxt, "列表摘要沒有露出 HTML 標籤")

shutil.rmtree(TMP, ignore_errors=True)
print("\n失敗項目：", check.failed)
sys.exit(1 if check.failed else 0)
