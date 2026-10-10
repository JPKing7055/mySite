#!/usr/bin/env python3
"""Build the static blog section (blog/index.html and blog/posts/*.html).

Usage:  pip install markdown-it-py   &&   python3 tools/build_blog.py
Input:  tools/posts.json (post data), tools/blog_config.json (hidden posts, labels)
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


def render_body(p):
    tight = p["date"] < "2020"  # old diary posts: keep line breaks inside one paragraph
    out, buf, items, kind = [], [], [], None

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
    t = " ".join(l for l in p["md"].split("\n") if l and not l.startswith("<") and not l.startswith("\\[youtube"))
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
<a href="{root}index.html" class="font-bold text-xl tracking-wider text-slate-900 dark:text-white">PORTFOLIO<span class="text-sky-500 dark:text-sky-400">.</span></a>
<nav><ul class="flex space-x-6 md:space-x-8 text-sm font-medium">
<li><a href="{root}index.html" class="text-slate-600 hover:text-sky-500 dark:text-slate-300 dark:hover:text-sky-400 transition-colors">首頁</a></li>
<li><a href="{root}blog/index.html" class="text-sky-600 dark:text-sky-400">部落格</a></li>
</ul></nav>
</div></div></header>
<button id="theme-toggle" class="fixed bottom-6 right-6 z-50 w-12 h-12 rounded-full bg-white dark:bg-slate-800 text-slate-600 dark:text-amber-300 shadow-lg border border-slate-200 dark:border-slate-700 flex items-center justify-center hover:scale-110 transition-all focus:outline-none group" title="切換深淺色">
<i class="fas fa-sun text-xl block dark:hidden"></i><i class="fas fa-moon text-xl hidden dark:block"></i>
</button>
"""

FOOT = """<footer class="bg-slate-100 dark:bg-slate-950 py-10 border-t border-slate-200 dark:border-slate-800 mt-16">
<div class="max-w-6xl mx-auto px-6 lg:px-8 text-sm text-slate-500 dark:text-slate-400 flex flex-col sm:flex-row justify-between gap-2">
<span>© 2026 Personal Portfolio. All rights reserved.</span><a href="{root}index.html" class="hover:text-sky-500">← 回到首頁</a>
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


def build_index():
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
<h1 class="text-3xl md:text-4xl font-bold text-slate-900 dark:text-white mb-2">部落格</h1>
<div class="w-20 h-1 bg-sky-500 rounded mx-auto mb-4"></div>
<p class="text-slate-600 dark:text-slate-400">遊戲產業、AI、虛擬創作的想法，以及舊部落格的文章存檔。</p>
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
    (OUT / "index.html").write_text(page("部落格 | Portfolio", "遊戲產業、AI、虛擬創作的想法與舊文存檔", "../", body, script), encoding="utf8")


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
<a href="../index.html" class="text-sm text-slate-500 dark:text-slate-400 hover:text-sky-500"><i class="fas fa-arrow-left mr-1"></i>返回部落格</a>
<article class="mt-6">
<div class="flex flex-wrap items-center gap-3 mb-3 text-sm text-slate-500 dark:text-slate-400"><time>{p['date']}</time><span class="{BADGE}">{esc(label(p['category']))}</span></div>
<h1 class="text-2xl md:text-4xl font-bold text-slate-900 dark:text-white leading-snug mb-8">{esc(p['title'])}</h1>
<div class="post-body text-slate-700 dark:text-slate-300">
{render_body(p)}
{('<p class="note">本篇原文附有 %d 張圖片或影片，尚未移轉到這裡。</p>' % p['media']) if p.get('media') else ''}
</div>
</article>
{nav}
</main>
"""
        (d / f"{p['id']}.html").write_text(page(f"{p['title']} | 部落格", excerpt(p, 80), "../../", body), encoding="utf8")


def build_home_teaser():
    latest = posts[:3]
    cards = "".join(
        f'<a href="blog/posts/{p["id"]}.html" class="glass-card block rounded-2xl p-6 bg-white/70 dark:bg-[rgba(30,41,59,0.7)] border border-slate-200 dark:border-[rgba(255,255,255,0.1)] hover:border-sky-400/50 shadow-lg shadow-slate-200/50 dark:shadow-none transition-all reveal">'
        f'<div class="text-sm text-slate-500 dark:text-slate-400 mb-2">{p["date"]}・{esc(label(p["category"]))}</div>'
        f'<h3 class="text-lg font-bold text-slate-900 dark:text-white mb-2">{esc(p["title"])}</h3>'
        f'<p class="text-slate-600 dark:text-slate-400 leading-relaxed text-sm">{esc(excerpt(p, 70))}</p></a>'
        for p in latest
    )
    block = f"""<!-- BLOG-LATEST:START (auto-generated by tools/build_blog.py) -->
        <section id="blog" class="py-24 px-6 sm:px-8 transition-colors duration-500">
            <div class="max-w-6xl mx-auto">
                <div class="text-center mb-12 reveal">
                    <h2 class="text-3xl font-bold text-slate-900 dark:text-white mb-2 transition-colors">部落格</h2>
                    <div class="w-20 h-1 bg-sky-500 rounded mx-auto mb-4"></div>
                    <p class="text-slate-600 dark:text-slate-400 transition-colors">遊戲產業、AI、虛擬創作的一些想法。</p>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-6">{cards}</div>
                <div class="text-center mt-10">
                    <a href="blog/index.html" class="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-sky-500 hover:bg-sky-600 text-white font-medium transition-all shadow-lg">查看全部 {len(posts)} 篇文章 <i class="fas fa-arrow-right"></i></a>
                </div>
            </div>
        </section>
        <!-- BLOG-LATEST:END -->"""
    f = ROOT / "index.html"
    t = f.read_text(encoding="utf8")
    t2 = re.sub(r"<!-- BLOG-LATEST:START.*?BLOG-LATEST:END -->", lambda m: block, t, flags=re.S)
    f.write_text(t2, encoding="utf8")


build_index(); build_posts(); build_home_teaser()
print(f"built {len(posts)} posts")
