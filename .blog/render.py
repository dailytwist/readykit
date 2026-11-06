"""Turns .blog/posts/*.json into guide pages, and updates guides.html and sitemap.xml. Uses guides.html as the page template."""
import json, re, html
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
URL = "https://readykitshop.com"
e = lambda s: html.escape(s, quote=True)

tpl = (ROOT / "guides.html").read_text()
head, rest = tpl.split("</head>", 1)
header = rest.split("<main", 1)[0]
footer = rest.split("</main>", 1)[1]
posts = sorted((json.loads(f.read_text()) for f in (HERE / "posts").glob("*.json")), key=lambda p: (p["date"], p["slug"]), reverse=True)


def set_meta(h, title, desc, url, img):
    h = re.sub(r"<title>.*?</title>", f"<title>{e(title)}</title>", h, flags=re.S)
    h = re.sub(r'(<meta name="description" content=")[^"]*', lambda m: m.group(1) + e(desc), h)
    h = re.sub(r'(<link rel="canonical" href=")[^"]*', lambda m: m.group(1) + url, h)
    h = re.sub(r'(<meta property="og:title" content=")[^"]*', lambda m: m.group(1) + e(title), h)
    h = re.sub(r'(<meta property="og:description" content=")[^"]*', lambda m: m.group(1) + e(desc), h)
    h = re.sub(r'(<meta property="og:image" content=")[^"]*', lambda m: m.group(1) + img, h)
    return h.replace('<meta property="og:type" content="website">', '<meta property="og:type" content="article">')


def product(slug):
    s = (ROOT / f"{slug}.html").read_text()
    name = re.sub(r"<[^>]+>", "", re.search(r"<h1>(.*?)</h1>", s, re.S).group(1))
    img = re.search(r'id="mainimg" src="([^"]+)"', s)
    price = re.search(r'class="amount">([^<]+)<', s)
    lede = re.search(r'class="lede">(.*?)</p>', s, re.S)
    return {"name": name, "img": img.group(1) if img else "img/bundle.jpg", "price": price.group(1) if price else "",
            "lede": re.sub(r"<[^>]+>", "", lede.group(1)) if lede else ""}


def short(t, n=140):
    first = re.split(r"(?<=[.!?])\s", t)[0]
    return first if len(first) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def cta(pr, slug):
    return (f'<aside class="guide-cta" style="display:flex;gap:16px;align-items:center;border:1px solid #e3e6f0;border-radius:16px;padding:16px;margin:28px 0;background:#fafbff">'
            f'<img src="{pr["img"]}" alt="{e(pr["name"])}" width="120" height="90" loading="lazy" style="width:120px;height:auto;border-radius:10px;flex:none">'
            f'<div><b>{e(pr["name"])}</b><p style="margin:6px 0 10px">{e(short(pr["lede"]))}</p><a class="btn" href="{slug}.html">See the template{" · " + e(pr["price"]) if pr["price"] else ""}</a></div></aside>')


for p in posts:
    pr = product(p["product"])
    url = f"{URL}/{p['slug']}.html"
    secs = p["sections"]
    mid = len(secs) // 2
    body = "".join((cta(pr, p["product"]) if i == mid else "") + f"<h2>{e(s['h2'])}</h2>{s['html']}" for i, s in enumerate(secs))
    faq = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in p["faq"])
    related = [o for o in posts if o["slug"] != p["slug"] and o["product"] == p["product"]][:3] or [o for o in posts if o["slug"] != p["slug"]][:3]
    rel = "".join(f'<li><a href="{o["slug"]}.html">{e(o["title"])}</a></li>' for o in related)
    ld = [{"@context": "https://schema.org", "@type": "Article", "headline": p["title"], "description": p["description"], "datePublished": p["date"],
           "dateModified": p["date"], "image": f"{URL}/{pr['img']}", "mainEntityOfPage": url,
           "author": {"@type": "Organization", "name": "ReadyKit"}, "publisher": {"@type": "Organization", "name": "ReadyKit"}},
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{URL}/"},
              {"@type": "ListItem", "position": 2, "name": "Guides", "item": f"{URL}/guides.html"},
              {"@type": "ListItem", "position": 3, "name": p["title"], "item": url}]},
          {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
              {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in p["faq"]]}]
    h = set_meta(head, p["title"] + " | ReadyKit", p["description"], url, f"{URL}/{pr['img']}")
    h += "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in ld)
    main = (f'<main class="wrap doc"><p class="crumbs"><a href="index.html">Home</a> / <a href="guides.html">Guides</a></p>'
            f'<h1>{e(p["title"])}</h1><p class="small">Updated {p["date"]}</p>{p["intro"]}{body}'
            f'<h2>Questions people ask</h2>{faq}{cta(pr, p["product"])}'
            + (f'<h2>More guides</h2><ul>{rel}</ul>' if rel else "") + '</main>')
    (ROOT / f"{p['slug']}.html").write_text(h + "</head>" + header + main + footer)

# guides index: new posts first, then the hand-written guides already listed
mine = {p["slug"] + ".html" for p in posts}
old = [(a, t, d) for a, t, d in re.findall(r'<h2><a href="([^"]+)">(.*?)</a></h2><p>(.*?)</p>', tpl, re.S) if a not in mine]
items = [(p["slug"] + ".html", e(p["title"]), e(p["description"])) for p in posts] + old
lst = "".join(f'<h2><a href="{a}">{t}</a></h2><p>{d}</p>' for a, t, d in items)
gmain = re.search(r'<main class="wrap doc">.*?</main>', tpl, re.S).group(0)
intro = re.search(r'<main class="wrap doc">(<h1>.*?</h1><p>.*?</p>)', gmain, re.S).group(1)
(ROOT / "guides.html").write_text(tpl.replace(gmain, f'<main class="wrap doc">{intro}{lst}</main>'))

# sitemap
sm = (ROOT / "sitemap.xml").read_text()
have = set(re.findall(r"<loc>(.*?)</loc>", sm))
add = "".join(f"<url><loc>{URL}/{p['slug']}.html</loc><lastmod>{p['date']}</lastmod></url>" for p in posts if f"{URL}/{p['slug']}.html" not in have)
(ROOT / "sitemap.xml").write_text(sm.replace("</urlset>", add + "</urlset>"))
print(f"rendered {len(posts)} posts, guides list has {len(items)} entries")

# product pages: link to the guides written for them (internal links help Google find and rank both)
for f in ROOT.glob("*.html"):
    s = f.read_text()
    if '<section class="pp-more">' not in s:
        continue
    slug = f.stem
    mine = [p for p in posts if p["product"] == slug][:4]
    block = ""
    if mine:
        block = ('<!--guides--><section class="pp-guides" style="margin:8px 0 32px"><h2>Free guides</h2><ul>'
                 + "".join(f'<li><a href="{p["slug"]}.html">{e(p["title"])}</a></li>' for p in mine) + "</ul></section><!--/guides-->")
    s2 = re.sub(r"<!--guides-->.*?<!--/guides-->", "", s, flags=re.S).replace('<section class="pp-more">', block + '<section class="pp-more">', 1)
    if s2 != s:
        f.write_text(s2)
