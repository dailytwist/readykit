"""Writes one new ReadyKit guide with Google Gemini (free tier) and saves it to .blog/posts/<slug>.json.
Picks the next topic from topics.json that has no post yet. Needs the GEMINI_API_KEY secret."""
import json, os, re, sys, time, urllib.request, datetime as dt
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
POSTS = HERE / "posts"
POSTS.mkdir(exist_ok=True)
KEY = os.environ.get("GEMINI_API_KEY", "")


def slugify(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")[:70].strip("-")


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"x-goog-api-key": KEY, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def models():
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", headers={"x-goog-api-key": KEY})
    with urllib.request.urlopen(req, timeout=60) as r:
        names = [m["name"].split("/", 1)[1] for m in json.loads(r.read()).get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
    def score(n):  # free tier: Flash first, then Flash-Lite; Pro has no free quota
        bad = any(x in n for x in ("preview", "exp", "tts", "image", "live", "audio", "embedding", "robotics", "gemma", "pro", "thinking"))
        ver = [int(x) for x in re.findall(r"\d+", n)[:2]] + [0, 0]
        return (not bad, "flash" in n, "lite" not in n, ver[0], ver[1])
    return [n for n in sorted(names, key=score, reverse=True) if "flash" in n][:6]


def ask(prompt):
    last = ""
    for model in models():
        for attempt in range(3):
            try:
                d = post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                         {"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"maxOutputTokens": 8000, "temperature": 0.7, "responseMimeType": "application/json"}})
                t = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
                t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t.strip())
                return json.loads(t[t.find("{"):]), model
            except Exception as e:
                last = f"{model}: {e}"
                print("  retry:", last)
                time.sleep(30 if "429" in str(e) else 45 if "503" in str(e) else 8)
                if "404" in str(e) or ("429" in str(e) and attempt >= 1):
                    break
    raise RuntimeError(last)


ALLOWED = re.compile(r"</?(?:p|ul|ol|li|strong|em|b|i)>")


def clean(html):
    html = re.sub(r"<(?!/?(?:p|ul|ol|li|strong|em|b|i)>)[^>]*>", "", html)  # only simple tags survive
    return html.strip()


def words(p):
    txt = " ".join([p["intro"]] + [s["html"] for s in p["sections"]] + [a for _, a in p["faq"]])
    return len(re.sub(r"<[^>]+>", " ", txt).split())


BANNED = re.compile(r"guarantee|get rich|passive income|cure|lose \d+ ?(?:kg|lbs|pounds)|doctor recommended|\$\d{3,}[^.]{0,30}(?:per|a) (?:month|day)", re.I)


def main():
    if not KEY:
        print("::error::GEMINI_API_KEY secret is missing in this repository (Settings > Secrets and variables > Actions).")
        sys.exit(1)
    topics = json.loads((HERE / "topics.json").read_text())
    done = {json.loads(f.read_text())["kw"] for f in POSTS.glob("*.json")}
    todo = [t for t in topics if t["kw"] not in done]
    if not todo:
        print("All topics written. Add new ones to .blog/topics.json")
        return
    t = todo[0]
    page = (ROOT / f"{t['product']}.html").read_text()
    pname = re.sub(r"<[^>]+>", "", re.search(r"<h1>(.*?)</h1>", page, re.S).group(1))
    inside = re.findall(r"<li>(.*?)</li>", page.split("What's inside", 1)[-1].split("</ul>", 1)[0])
    prompt = f"""You write practical, trustworthy guides for ReadyKit, a small online shop selling printable planners and spreadsheet templates.
Write an original, genuinely useful English article for people searching Google for: "{t['kw']}".

Rules:
- 1000 to 1400 words in total. Clear, warm, plain English. Short paragraphs. Concrete steps, real examples, small worked numbers where useful.
- Answer the search question fully in the article itself; the reader must not need to buy anything to benefit.
- Mention the ReadyKit product "{pname}" naturally at most twice, only where it truly helps (it contains: {"; ".join(inside[:7])}). No hard selling.
- No made-up statistics, studies, quotes, prices of other brands or testimonials. No promises of income, savings amounts, weight loss or health results. No medical, legal or tax advice beyond general tips.
- For religious topics, be respectful and general; tell readers to follow their local mosque or scholars for rulings and dates.
- Use only these HTML tags inside "html": <p>, <ul>, <ol>, <li>, <strong>, <em>.

Return JSON exactly like:
{{"title": "SEO title, max 62 characters, includes the main keyword",
  "description": "meta description, 140-155 characters",
  "intro": "<p>2 short paragraphs that answer the question quickly</p>",
  "sections": [{{"h2": "section heading", "html": "<p>...</p>"}}],   (5 to 7 sections)
  "faq": [["question people also ask", "2-3 sentence answer"]]     (3 or 4 items)
}}"""
    for tries in range(3):
        p, model = ask(prompt)
        p["intro"] = clean(p["intro"])
        for s in p["sections"]:
            s["html"] = clean(s["html"]); s["h2"] = re.sub(r"<[^>]+>", "", s["h2"])
        p["faq"] = [[re.sub(r"<[^>]+>", "", q), re.sub(r"<[^>]+>", "", a)] for q, a in p["faq"]][:5]
        n = words(p); full = json.dumps(p)
        if n >= 800 and len(p["sections"]) >= 4 and not BANNED.search(full):
            break
        print(f"  rejected draft ({n} words, banned={bool(BANNED.search(full))}), trying again")
    else:
        print("::error::could not get a good article today"); sys.exit(1)
    slug = slugify(p["title"])
    if (ROOT / f"{slug}.html").exists():
        slug = slugify(t["kw"])
    p.update(kw=t["kw"], product=t["product"], slug=slug, date=dt.date.today().isoformat(), model=model)
    (POSTS / f"{slug}.json").write_text(json.dumps(p, ensure_ascii=False, indent=1))
    print(f"wrote {slug} ({words(p)} words, {model})")


if __name__ == "__main__":
    main()
