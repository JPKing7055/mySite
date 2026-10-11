#!/usr/bin/env python3
"""Build the static personal-space section.

Output pages: blog/index.html (now + sticky-note wall), blog/zone/*.html (one per zone),
blog/all.html (all posts with search/filter), blog/posts/*.html (articles).

Usage:  pip install markdown-it-py   &&   python3 tools/build_blog.py
Input:  tools/posts.json (post data), tools/blog_config.json (hidden posts, labels, now, zones)
Output: blog/ (commit it; GitHub Pages serves it as-is)
"""
import json, re, html, shutil
from pathlib import Path
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "blog"
posts = json.load(open(ROOT / "tools/posts.json", encoding="utf8"))
cfg = json.load(open(ROOT / "tools/blog_config.json", encoding="utf8"))
hidden = set(cfg.get("hidden_ids", []))
labels = cfg.get("category_labels", {})
order = cfg.get("category_order", [])
posts = [p for p in posts if p["id"] not in hidden]
posts.sort(key=lambda p: (p["date"], p["id"]), reverse=True)

md = MarkdownIt("commonmark", {"html": True})
label = lambda c: labels.get(c, c)
esc = lambda s: html.escape(s, quote=True)


def inline(t):
    return md.renderInline(t)


IMG_DIR = Path(__file__).resolve().parent.parent / "blog" / "img"
# 內文裡單獨一行 [圖:檔名.png] 或 [圖:檔名.png|圖說] 會顯示 blog/img/ 裡的圖片
IMG_RE = re.compile(r"^\[圖[:：]\s*([A-Za-z0-9_.\-]+\.(?:png|jpe?g|gif|webp))\s*(?:[|｜]\s*([^\]]*))?\]$", re.I)


def render_body(p):
    tight = p["date"] < "2020"  # old diary posts: keep line breaks inside one paragraph
    out, buf, items, kind = [], [], [], None
    p["_imgs"] = 0

    def flush_p():
        if buf:
            out.append("<p>" + "<br>\n".join(inline(x) for x in buf) + "</p>")
            buf.clear()

    def flush_list():
        nonlocal kind, items
        if items:
            out.append(f"<{kind}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{kind}>")
        items, kind = [], None

    for raw in p["md"].split("\n"):
        s = raw.rstrip()
        if s == "<empty-block/>" or not s:
            flush_list(); flush_p(); continue
        mi = IMG_RE.match(s)
        if mi:
            flush_list(); flush_p()
            fn, cap = mi.group(1), (mi.group(2) or "").strip()
            if not (IMG_DIR / fn).exists():
                print(f"WARNING: post {p['id']} ({p['title']}): image not found: blog/img/{fn}")
            cap_html = f"<figcaption>{esc(cap)}</figcaption>" if cap else ""
            out.append(f'<figure><img src="../img/{esc(fn)}" alt="{esc(cap)}" loading="lazy">{cap_html}</figure>')
            p["_imgs"] += 1
            continue
        if s.startswith('<span color="gray">'):
            flush_list(); flush_p()
            t = re.sub(r"</?span[^>]*>", "", s)
            out.append(f'<p class="note">{esc(t)}</p>')
            continue
        if s == "---":
            flush_list(); flush_p(); out.append("<hr>"); continue
        m = re.match(r"^(#{1,3}) (.*)", s)
        if m:
            flush_list(); flush_p()
            lv = len(m.group(1)) + 1
            out.append(f"<h{lv}>{inline(m.group(2))}</h{lv}>"); continue
        m = re.match(r"^- (.*)", s)
        if m:
            flush_p()
            if kind not in (None, "ul"): flush_list()
            kind = "ul"; items.append(m.group(1)); continue
        m = re.match(r"^\d+\. (.*)", s)
        if m:
            flush_p()
            if kind not in (None, "ol"): flush_list()
            kind = "ol"; items.append(m.group(1)); continue
        if s.startswith("> "):
            flush_list(); flush_p(); out.append(f"<blockquote>{inline(s[2:])}</blockquote>"); continue
        flush_list()
        if tight:
            buf.append(s)
        else:
            out.append(f"<p>{inline(s)}</p>")
    flush_list(); flush_p()
    return "\n".join(out)


def excerpt(p, n=90):
    t = " ".join(l for l in p["md"].split("\n") if l and not l.startswith("<") and not l.startswith("[圖") and not l.startswith("\\[youtube"))
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[\\*~`#>]|^- ", "", t)
    t = re.sub(r"https?://\S+", "", t).strip()
    return (t[:n] + "…") if len(t) > n else t


HEAD = """<!DOCTYPE html>
<html lang="zh-TW" class="scroll-smooth dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config = { darkMode: 'class' }</script>
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&family=Noto+Sans+TC:wght@300;400;500;700&display=swap');
body { font-family: 'Inter', 'Noto Sans TC', sans-serif; overflow-x: hidden; }
.dark ::-webkit-scrollbar-track { background: #0f172a; } .dark ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
::-webkit-scrollbar { width: 8px; } ::-webkit-scrollbar-track { background: #f1f5f9; } ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
.post-body { font-size: 1.08rem; line-height: 2; }
.post-body p { margin: 0 0 1.4em; overflow-wrap: anywhere; }
.post-body h2, .post-body h3, .post-body h4 { font-weight: 700; margin: 2em 0 .8em; color: inherit; }
.post-body h2 { font-size: 1.5rem; } .post-body h3 { font-size: 1.25rem; }
.post-body ul, .post-body ol { margin: 0 0 1.4em 1.5em; } .post-body ul { list-style: disc; } .post-body ol { list-style: decimal; }
.post-body li { margin: .3em 0; }
.post-body a { color: #0ea5e9; text-decoration: underline; text-underline-offset: 3px; overflow-wrap: anywhere; }
.post-body figure { margin: 0 0 1.6em; } .post-body figure img { max-width: 100%; height: auto; border-radius: .75rem; border: 1px solid rgba(148,163,184,.3); }
.post-body figcaption { font-size: .875rem; opacity: .65; margin-top: .5em; text-align: center; }
.post-body hr { margin: 2em 0; border-color: rgba(148,163,184,.4); }
.post-body blockquote { border-left: 3px solid #38bdf8; padding-left: 1em; margin: 0 0 1.4em; opacity: .85; }
.post-body .note { font-size: .875rem; opacity: .6; border-top: 1px dashed rgba(148,163,184,.5); padding-top: 1em; margin-top: 2em; }
</style>
</head>
<body class="antialiased selection:bg-sky-500 selection:text-white relative bg-slate-50 text-slate-700 dark:bg-[#0f172a] dark:text-slate-300 transition-colors duration-500">
<div class="fixed top-0 left-0 w-full h-full overflow-hidden -z-10 pointer-events-none">
<div class="absolute top-[-10%] left-[-10%] w-96 h-96 bg-sky-400/20 dark:bg-sky-600/20 rounded-full blur-3xl"></div>
<div class="absolute bottom-[-10%] right-[-10%] w-96 h-96 bg-indigo-400/20 dark:bg-indigo-600/20 rounded-full blur-3xl"></div>
</div>
<header class="fixed w-full top-0 z-40 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-b border-slate-200 dark:border-slate-800">
<div class="max-w-6xl mx-auto px-6 lg:px-8"><div class="flex items-center justify-between h-16">
<a href="{root}index.html" class="hidden sm:block font-bold text-xl tracking-wider text-slate-900 dark:text-white">JPK<span class="text-sky-500 dark:text-sky-400"> Lab</span></a>
<nav><ul class="flex space-x-4 sm:space-x-5 md:space-x-8 text-[13px] sm:text-sm font-medium">
<li><a href="{root}index.html" class="text-slate-600 hover:text-sky-500 dark:text-slate-300 dark:hover:text-sky-400 transition-colors">首頁</a></li>
<li><a href="{root}resume.html" class="text-slate-600 hover:text-sky-500 dark:text-slate-300 dark:hover:text-sky-400 transition-colors">成員專長</a></li>
<li><a href="{root}portfolio/index.html" class="text-slate-600 hover:text-sky-500 dark:text-slate-300 dark:hover:text-sky-400 transition-colors">成員作品</a></li>
<li><a href="{root}blog/index.html" class="text-sky-600 dark:text-sky-400 font-semibold">成員個人空間</a></li>
</ul></nav>
</div></div></header>
<button id="theme-toggle" class="fixed bottom-6 right-6 z-50 w-12 h-12 rounded-full bg-white dark:bg-slate-800 text-slate-600 dark:text-amber-300 shadow-lg border border-slate-200 dark:border-slate-700 flex items-center justify-center hover:scale-110 transition-all focus:outline-none group" title="切換深淺色">
<i class="fas fa-sun text-xl block dark:hidden"></i><i class="fas fa-moon text-xl hidden dark:block"></i>
</button>
"""

FOOT = """<footer class="bg-slate-100 dark:bg-slate-950 py-10 border-t border-slate-200 dark:border-slate-800 mt-16">
<div class="max-w-6xl mx-auto px-6 lg:px-8 text-sm text-slate-500 dark:text-slate-400 flex flex-col sm:flex-row justify-between gap-2">
<span>© 2026 JPK Lab. All rights reserved.</span><a href="{root}index.html" class="hover:text-sky-500">← 回到首頁</a>
</div></footer>
<script>
(function () {
  var el = document.documentElement;
  try {
    if (localStorage.theme === 'light' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: light)').matches)) el.classList.remove('dark'); else el.classList.add('dark');
  } catch (e) { el.classList.add('dark'); }
  document.getElementById('theme-toggle').addEventListener('click', function () {
    el.classList.toggle('dark');
    try { localStorage.theme = el.classList.contains('dark') ? 'dark' : 'light'; } catch (e) {}
  });
})();
</script>
{extra}
</body></html>
"""

BADGE = "inline-block text-xs px-2.5 py-1 rounded-full bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300 border border-sky-200 dark:border-sky-500/30"


def page(title, desc, root, body, extra=""):
    head = HEAD.replace("{title}", esc(title)).replace("{desc}", esc(desc)).replace("{root}", root)
    foot = FOOT.replace("{root}", root).replace("{extra}", extra)
    return head + body + foot


def card(p, root):
    href = f"{root}blog/posts/{p['id']}.html"
    return (
        f'<a href="{href}" class="post-card block glass rounded-2xl p-6 bg-white/70 dark:bg-slate-800/70 border border-slate-200 dark:border-white/10 hover:border-sky-400/60 shadow-sm transition-all" '
        f'data-cat="{esc(p["category"])}" data-year="{p["date"][:4]}" data-text="{esc((p["title"] + " " + excerpt(p, 200)).lower())}">'
        f'<div class="flex flex-wrap items-center gap-3 mb-2 text-sm text-slate-500 dark:text-slate-400"><time>{p["date"]}</time>'
        f'<span class="{BADGE}">{esc(label(p["category"]))}</span></div>'
        f'<h3 class="text-lg md:text-xl font-bold text-slate-900 dark:text-white mb-2">{esc(p["title"])}</h3>'
        f'<p class="text-slate-600 dark:text-slate-400 leading-relaxed">{esc(excerpt(p))}</p></a>'
    )


def build_all():
    cats = {}
    for p in posts: cats[p["category"]] = cats.get(p["category"], 0) + 1
    ordered = [c for c in order if c in cats] + [c for c in cats if c not in order]
    chips = '<button data-filter="" class="chip active">全部 <span class="opacity-60">%d</span></button>' % len(posts)
    chips += "".join(f'<button data-filter="{esc(c)}" class="chip">{esc(label(c))} <span class="opacity-60">{cats[c]}</span></button>' for c in ordered)
    years = sorted({p["date"][:4] for p in posts}, reverse=True)
    blocks = []
    for y in years:
        cs = "\n".join(card(p, "../") for p in posts if p["date"][:4] == y)
        blocks.append(f'<section class="year-block" data-year="{y}"><h2 class="text-2xl font-bold text-slate-900 dark:text-white mt-12 mb-4 flex items-center gap-3">{y}<span class="flex-1 h-px bg-slate-200 dark:bg-slate-700"></span></h2><div class="grid gap-4">{cs}</div></section>')
    body = f"""<main class="max-w-3xl mx-auto px-6 pt-28">
<div class="text-center mb-10">
<a href="index.html" class="text-sm text-slate-500 dark:text-slate-400 hover:text-sky-500"><i class="fas fa-arrow-left mr-1"></i>返回個人空間</a>
<h1 class="text-3xl md:text-4xl font-bold text-slate-900 dark:text-white mt-4 mb-2">全部文章</h1>
<div class="w-20 h-1 bg-sky-500 rounded mx-auto mb-4"></div>
<p class="text-slate-600 dark:text-slate-400">依年份列出所有文章，可搜尋與依分類篩選。</p>
</div>
<style>
.chip {{ padding: .35rem .9rem; border-radius: 9999px; font-size: .875rem; border: 1px solid rgba(148,163,184,.5); background: transparent; cursor: pointer; transition: all .2s; }}
.chip:hover {{ border-color: #38bdf8; color: #0ea5e9; }}
.chip.active {{ background: #0ea5e9; border-color: #0ea5e9; color: #fff; }}
.chip.active span {{ opacity: .8; }}
</style>
<div class="relative mb-4"><i class="fas fa-search absolute left-4 top-1/2 -translate-y-1/2 text-slate-400"></i>
<input id="q" type="search" placeholder="搜尋標題或內文開頭" class="w-full pl-11 pr-4 py-3 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:border-sky-400 text-slate-800 dark:text-slate-100"></div>
<div id="chips" class="flex flex-wrap gap-2 mb-2">{chips}</div>
<p id="count" class="text-sm text-slate-500 dark:text-slate-400 mt-4"></p>
{"".join(blocks)}
<p id="empty" class="hidden text-center text-slate-500 py-16">沒有符合的文章。</p>
</main>
"""
    script = """<script>
(function () {
  var cards = [].slice.call(document.querySelectorAll('.post-card'));
  var blocks = [].slice.call(document.querySelectorAll('.year-block'));
  var q = document.getElementById('q'), count = document.getElementById('count'), empty = document.getElementById('empty');
  var cat = '';
  function apply() {
    var kw = q.value.trim().toLowerCase(), shown = 0;
    cards.forEach(function (c) {
      var ok = (!cat || c.dataset.cat === cat) && (!kw || c.dataset.text.indexOf(kw) > -1);
      c.style.display = ok ? '' : 'none'; if (ok) shown++;
    });
    blocks.forEach(function (b) { b.style.display = b.querySelector('.post-card:not([style*="none"])') ? '' : 'none'; });
    count.textContent = '共 ' + shown + ' 篇';
    empty.classList.toggle('hidden', shown > 0);
  }
  document.getElementById('chips').addEventListener('click', function (e) {
    var b = e.target.closest('.chip'); if (!b) return;
    [].forEach.call(document.querySelectorAll('.chip'), function (x) { x.classList.remove('active'); });
    b.classList.add('active'); cat = b.dataset.filter; apply();
  });
  q.addEventListener('input', apply); apply();
})();
</script>"""
    (OUT).mkdir(exist_ok=True)
    (OUT / "all.html").write_text(page("全部文章 | JP 的個人空間", "所有文章，可搜尋與依分類篩選", "../", body, script), encoding="utf8")


def build_posts():
    d = OUT / "posts"
    if d.exists(): shutil.rmtree(d)
    d.mkdir(parents=True)
    for i, p in enumerate(posts):
        newer = posts[i - 1] if i > 0 else None
        older = posts[i + 1] if i + 1 < len(posts) else None
        nav = '<nav class="mt-14 pt-6 border-t border-slate-200 dark:border-slate-700 grid sm:grid-cols-2 gap-4 text-sm">'
        nav += (f'<a href="{older["id"]}.html" class="block p-4 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-sky-400"><span class="text-slate-500 dark:text-slate-400">← 上一篇</span><br><span class="font-semibold text-slate-800 dark:text-slate-100">{esc(older["title"])}</span></a>' if older else "<span></span>")
        nav += (f'<a href="{newer["id"]}.html" class="block p-4 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-sky-400 sm:text-right"><span class="text-slate-500 dark:text-slate-400">下一篇 →</span><br><span class="font-semibold text-slate-800 dark:text-slate-100">{esc(newer["title"])}</span></a>' if newer else "<span></span>")
        nav += "</nav>"
        body = f"""<main class="max-w-3xl mx-auto px-6 pt-28">
<a href="../index.html" class="text-sm text-slate-500 dark:text-slate-400 hover:text-sky-500"><i class="fas fa-arrow-left mr-1"></i>返回個人空間</a>
<article class="mt-6">
<div class="flex flex-wrap items-center gap-3 mb-3 text-sm text-slate-500 dark:text-slate-400"><time>{p['date']}</time><span class="{BADGE}">{esc(label(p['category']))}</span></div>
<h1 class="text-2xl md:text-4xl font-bold text-slate-900 dark:text-white leading-snug mb-8">{esc(p['title'])}</h1>
<div class="post-body text-slate-700 dark:text-slate-300">
{render_body(p)}
{('<p class="note">本篇原文附有 %d 張圖片或影片，尚未移轉到這裡。</p>' % (p['media'] - p.get('_imgs', 0))) if p.get('media', 0) - p.get('_imgs', 0) > 0 else ''}
</div>
</article>
{nav}
</main>
"""
        (d / f"{p['id']}.html").write_text(page(f"{p['title']} | JP 的個人空間", excerpt(p, 80), "../../", body), encoding="utf8")

NOTE_CSS = """<style>
.note { position: relative; display: flex; flex-direction: column; min-height: 11rem; padding: 1.75rem 1.4rem 1.2rem; background: var(--bg); color: #1e293b;
  box-shadow: 0 10px 18px -6px rgba(0,0,0,.35); border-radius: 3px 3px 12px 3px; transform: rotate(var(--r, 0deg)); transition: transform .2s, box-shadow .2s; }
.note::before { content: ""; position: absolute; top: -10px; left: 50%; width: 64px; height: 20px; margin-left: -32px; background: rgba(255,255,255,.55); box-shadow: 0 1px 2px rgba(0,0,0,.15); transform: rotate(-2deg); }
.note:nth-child(3n+1) { --r: -1.2deg; } .note:nth-child(3n+2) { --r: .9deg; } .note:nth-child(3n) { --r: -.4deg; }
a.note:hover { transform: rotate(0deg) translateY(-6px) scale(1.02); box-shadow: 0 18px 24px -8px rgba(0,0,0,.4); }
.note h3 { font-size: 1.25rem; font-weight: 800; margin-bottom: .5rem; }
.note p { color: #334155; line-height: 1.7; font-size: .95rem; flex: 1; }
.note .meta { margin-top: 1rem; font-size: .8rem; color: #475569; display: flex; justify-content: space-between; gap: .5rem; }
.note.empty { cursor: default; }
</style>"""


def zone_posts(z):
    return [p for p in posts if p["category"] in z["categories"]]


def build_home():
    zones = cfg.get("zones", [])
    covered = {c for z in zones for c in z["categories"]}
    for p in posts:
        if p["category"] not in covered:
            print(f"WARNING: post {p['id']} category '{p['category']}' is in no zone (only listed in all.html)")
    now = cfg.get("now")
    now_html = ""
    if now:
        paras = now["paragraphs"]
        body_html = f'<p class="text-2xl md:text-3xl font-bold text-slate-900 dark:text-white leading-snug mb-3">{esc(paras[0])}</p>'
        body_html += "".join(f'<p class="text-lg text-slate-700 dark:text-slate-300 leading-relaxed mb-3">{esc(t)}</p>' for t in paras[1:])
        now_html = (
            '<section class="mb-14 rounded-2xl p-8 md:p-10 border border-sky-300/60 dark:border-sky-500/30 bg-gradient-to-br from-sky-50 to-indigo-50 dark:from-slate-800 dark:to-slate-800/50 shadow-lg">'
            f'<div class="flex items-center gap-2 mb-4 text-sky-600 dark:text-sky-400 font-semibold tracking-wide"><i class="fas fa-bolt"></i><span>{esc(now["title"])}</span></div>'
            f'{body_html}<p class="text-sm text-slate-500 dark:text-slate-400 mt-4">更新於 {esc(now["updated"])}</p></section>'
        )
    notes = []
    for z in zones:
        zp = zone_posts(z)
        style = f'style="--bg:{z["color"]}"'
        if zp:
            meta = f'<div class="meta"><span>{len(zp)} 篇</span><span>最近 {zp[0]["date"]}</span></div>'
            notes.append(f'<a href="zone/{z["slug"]}.html" class="note" {style}><h3>{esc(z["name"])}</h3><p>{esc(z["summary"])}</p>{meta}</a>')
        else:
            meta = '<div class="meta"><span>尚無文章</span></div>'
            notes.append(f'<div class="note empty" {style}><h3>{esc(z["name"])}</h3><p>{esc(z["summary"])}</p>{meta}</div>')
    body = f"""<main class="max-w-5xl mx-auto px-6 pt-28">
<div class="text-center mb-10">
<h1 class="text-3xl md:text-4xl font-bold text-slate-900 dark:text-white mb-2">JP 的個人空間</h1>
<div class="w-20 h-1 bg-sky-500 rounded mx-auto mb-4"></div>
<p class="text-slate-600 dark:text-slate-400">興趣、研究與生活分享。</p>
</div>
{NOTE_CSS}
{now_html}
<section>
<div class="flex items-end justify-between mb-8"><h2 class="text-2xl font-bold text-slate-900 dark:text-white">專區</h2><span class="text-sm text-slate-500 dark:text-slate-400">點便條紙進去看文章</span></div>
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-10 pt-3">
{"".join(notes)}
</div>
</section>
<div class="text-center mt-16"><a href="all.html" class="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-sky-500 hover:bg-sky-600 text-white font-medium transition-all shadow-lg">查看全部 {len(posts)} 篇文章 <i class="fas fa-arrow-right"></i></a></div>
</main>
"""
    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(page("JP 的個人空間 | JPK Lab", "現在在做的事，以及興趣、研究與生活分享的專區", "../", body), encoding="utf8")


def build_zones():
    d = OUT / "zone"
    if d.exists(): shutil.rmtree(d)
    d.mkdir(parents=True)
    for z in cfg.get("zones", []):
        zp = zone_posts(z)
        if not zp: continue
        cards = "\n".join(card(p, "../../") for p in zp)
        body = f"""<main class="max-w-3xl mx-auto px-6 pt-28">
<a href="../index.html" class="text-sm text-slate-500 dark:text-slate-400 hover:text-sky-500"><i class="fas fa-arrow-left mr-1"></i>返回個人空間</a>
<div class="mt-6 mb-10 rounded-xl p-6" style="background:{z['color']};color:#1e293b">
<h1 class="text-3xl font-extrabold mb-2">{esc(z['name'])}</h1>
<p style="color:#334155">{esc(z['summary'])}</p>
<p class="text-sm mt-3" style="color:#475569">共 {len(zp)} 篇</p>
</div>
<div class="grid gap-4">{cards}</div>
</main>
"""
        (d / f"{z['slug']}.html").write_text(page(f"{z['name']} | JP 的個人空間", z["summary"], "../../", body), encoding="utf8")


build_all(); build_home(); build_zones(); build_posts()
print(f"built {len(posts)} posts")
