#!/usr/bin/env python3
"""
AVC One Thing — Full Pipeline
Perplexity → Claude → HTML pages + OG images → GitHub Pages → Telegram
"""

import os
import json
import requests
import subprocess
from datetime import datetime
from pathlib import Pat
import anthropic
from PIL import Image, ImageDraw, ImageFont

# ── Config ────────────────────────────────────────────────────────────────────
PERPLEXITY_API_KEY  = os.environ["PERPLEXITY_API_KEY"]
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID    = os.environ["TELEGRAM_CHAT_ID"]
GITHUB_PAGES_URL    = os.environ.get("PAGES_URL", "https://meltckr.github.io/avc-one-thing")

TODAY      = datetime.now().strftime("%A, %B %-d, %Y")
TODAY_SLUG = datetime.now().strftime("%Y-%m-%d")
DOCS_DIR   = Path("docs")
DOCS_DIR.mkdir(exist_ok=True)

BRAND = {
    "navy":       "#0B1D3A",
    "deep_navy":  "#0F2340",
    "gold":       "#C8A45C",
    "blue":       "#60a5fa",
    "blue_arrow": "#93c5fd",
    "divider":    "#334155",
    "white":      "#F1F5F9",
    "muted":      "rgba(255,255,255,0.45)",
}

TYPE_EMOJI  = {"INTEL": "📊", "LEADERSHIP": "♟️", "LENS": "🔭", "WILDCARD": "⚡"}
TYPE_LABEL  = {"INTEL": "Market Intelligence", "LEADERSHIP": "Leadership Move",
               "LENS": "Decision Lens", "WILDCARD": "Signal"}

# ── Fonts ─────────────────────────────────────────────────────────────────────
FONT_DIR = Path("/tmp/avc_fonts")
FONT_DIR.mkdir(exist_ok=True)

def download_font(url: str, dest: Path) -> None:
    if not dest.exists():
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        dest.write_bytes(r.content)

def get_fonts() -> dict:
    base = "https://github.com/google/fonts/raw/main/ofl"
    files = {
        "sans_regular": (f"{base}/dmsans/DMSans%5Bopsz,wght%5D.ttf", "DMSans-Regular.ttf"),
        "sans_bold":    (f"{base}/dmsans/DMSans%5Bopsz,wght%5D.ttf", "DMSans-Bold.ttf"),
        "serif":        (f"{base}/dmserifdisplay/DMSerifDisplay-Regular.ttf", "DMSerifDisplay.ttf"),
    }
    paths = {}
    for key, (url, fname) in files.items():
        dest = FONT_DIR / fname
        try:
            download_font(url, dest)
            paths[key] = str(dest)
        except Exception:
            paths[key] = None
    return paths

def load_pil_font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()

# ── Stage 1: Perplexity ───────────────────────────────────────────────────────
def fetch_signals() -> str:
    print("📡 Fetching signals from Perplexity...")
    prompt = f"""Today is {TODAY}. Search for the most relevant and timely news from TODAY across these three domains:

1. NBA / Phoenix Suns — roster moves, league news, ownership decisions, coaching strategies, G League, Western Conference standings

2. UWM / Wholesale Mortgage — competitor moves (Rocket, loanDepot, Pennymac), rate environment, regulatory changes, market share shifts

3. Sports Business / Ownership / Leadership — notable decisions by team owners, CEOs, or executives in sports or adjacent industries

For each domain, return the 2-3 most specific, current, and relevant signals. Include names, numbers, and facts. Prioritize what happened in the last 24 hours."""

    resp = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"},
        json={"model": "sonar-pro", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2},
        timeout=30
    )
    resp.raise_for_status()
    signals = resp.json()["choices"][0]["message"]["content"]
    print(f"  ✅ {len(signals)} chars of signal data")
    return signals

# ── Stage 2: Claude generates candidates ──────────────────────────────────────
def generate_candidates(signals: str) -> list[dict]:
    print("🧠 Generating candidates with Claude...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system = """You generate "One Thing" briefings for Mat Ishbia — owner of the Phoenix Suns and CEO of UWM.

The format is simple and deliberate:

1. Start with something real that happened with the Phoenix Suns — a play, a dynamic, a decision, a result. Be specific. Name names. Use actual details from today's signals.

2. Extract the business concept hiding inside it. Not a lesson. Not advice. Just the underlying principle — expressed in clean, precise business language.

3. Stop there. No implication. No "here's what this means for you." No UWM mention. No call to action.

The reader is a highly competitive CEO. He will connect the dots himself. Your job is to put two things next to each other — the Suns moment and the concept — and leave space for his brain to do the rest.

Tone: sharp, spare, confident. No filler. No hedging. No exclamation points.

Produce exactly 4 candidates using this EXACT format:

###CANDIDATE_START###

NUMBER: [1-4]

TYPE: [INTEL / LEADERSHIP / LENS / WILDCARD]

HEADLINE: [6-8 words. The Suns observation. Specific and factual.]

BODY: [2-3 sentences. What happened with the Suns. Real details, real names, real context.]

CONCEPT: [2-3 sentences. The business principle inside it. No Suns mention. No UWM mention. Just the concept, clean.]

QUESTION: [One question. Optional — only include if it arises naturally. Can be left as a single evocative line or omitted entirely.]

###CANDIDATE_END###

No preamble. No postamble. Four blocks only."""

    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": f"Today's signals:\n\n{signals}\n\nGenerate 4 One Thing candidates."}]
    )
    raw = resp.content[0].text
    candidates = parse_candidates(raw)
    print(f"  ✅ {len(candidates)} candidates generated")
    return candidates

def parse_candidates(raw: str) -> list[dict]:
    candidates = []
    for block in raw.split("###CANDIDATE_START###"):
        if "###CANDIDATE_END###" not in block:
            continue
        content = block.split("###CANDIDATE_END###")[0].strip()
        c = {}
        for line in content.splitlines():
            for key in ["NUMBER", "TYPE", "HEADLINE", "BODY", "CONCEPT", "QUESTION"]:
                if line.startswith(f"{key}:"):
                    c[key.lower()] = line[len(key)+1:].strip()
        if len(c) >= 5:
            candidates.append(c)
    return candidates

# ── Stage 3: Build HTML page per candidate ────────────────────────────────────
HTML_TEMPLATE = '''<!DOCTYPE html>

<html lang="en">

<head>

  <meta charset="UTF-8" />

  <meta name="viewport" content="width=device-width, initial-scale=1.0" />

  <title>{headline} — AVC One Thing</title>

  <meta property="og:title" content="{headline}" />

  <meta property="og:description" content="{body_short}" />

  <meta property="og:image" content="{og_image_url}" />

  <meta property="og:image:width" content="1200" />

  <meta property="og:image:height" content="630" />

  <meta property="og:type" content="website" />

  <meta property="og:site_name" content="Accelerated Velocity Consulting" />

  <meta name="twitter:card" content="summary_large_image" />

  <meta name="twitter:image" content="{og_image_url}" />

  <link rel="preconnect" href="https://fonts.googleapis.com" />

  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />

  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Serif+Display&display=swap" rel="stylesheet" />

  <style>

    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{

      --navy:    #0B1D3A;

      --deep:    #0F2340;

      --gold:    #C8A45C;

      --blue:    #60a5fa;

      --arrow:   #93c5fd;

      --white:   #F1F5F9;

      --divider: rgba(255,255,255,0.08);

    }}

    html, body {{

      min-height: 100vh;

      background: var(--navy);

      color: var(--white);

      font-family: 'DM Sans', sans-serif;

      -webkit-font-smoothing: antialiased;

    }}

    body {{

      display: flex;

      flex-direction: column;

      align-items: center;

      justify-content: center;

      min-height: 100vh;

      padding: 2rem 1.5rem;

    }}

    .card {{

      width: 100%;

      max-width: 680px;

      background: var(--deep);

      border: 1px solid rgba(200,164,92,0.2);

      border-radius: 16px;

      padding: 2.5rem 2.5rem 2rem;

      position: relative;

      overflow: hidden;

    }}

    .card::before {{

      content: '';

      position: absolute;

      inset: 0;

      background: radial-gradient(ellipse at top left, rgba(96,165,250,0.06) 0%, transparent 60%);

      pointer-events: none;

    }}

    .top-bar {{

      display: flex;

      align-items: center;

      justify-content: space-between;

      margin-bottom: 2rem;

    }}

    .avc-logo {{ height: 32px; width: auto; }}

    .date {{

      font-size: 11px;

      letter-spacing: 0.2em;

      text-transform: uppercase;

      color: rgba(255,255,255,0.35);

    }}

    .type-badge {{

      display: inline-flex;

      align-items: center;

      gap: 6px;

      background: rgba(200,164,92,0.12);

      border: 1px solid rgba(200,164,92,0.3);

      border-radius: 6px;

      padding: 4px 12px;

      font-size: 11px;

      font-weight: 600;

      letter-spacing: 0.2em;

      text-transform: uppercase;

      color: var(--gold);

      margin-bottom: 1.25rem;

    }}

    h1 {{

      font-family: 'DM Serif Display', serif;

      font-size: clamp(1.6rem, 4vw, 2.2rem);

      font-weight: 400;

      line-height: 1.2;

      color: var(--white);

      margin-bottom: 1.25rem;

    }}

    .divider {{ height: 1px; background: var(--divider); margin: 1.5rem 0; }}

    .body-text {{

      font-size: 1rem;

      line-height: 1.7;

      color: rgba(255,255,255,0.75);

      margin-bottom: 1.5rem;

    }}

    .concept {{

      background: rgba(96,165,250,0.07);

      border-left: 3px solid var(--blue);

      border-radius: 0 8px 8px 0;

      padding: 1rem 1.25rem;

      margin-bottom: 1.5rem;

    }}

    

    .concept-text {{ font-size: 0.9rem; line-height: 1.6; color: rgba(255,255,255,0.8); }}

    .question-label {{

      font-size: 10px;

      letter-spacing: 0.25em;

      text-transform: uppercase;

      color: var(--gold);

      font-weight: 600;

      margin-bottom: 0.5rem;

      display: flex;

      align-items: center;

      gap: 8px;

    }}

    .question-label::before {{

      content: '';

      display: block;

      width: 24px;

      height: 1px;

      background: var(--gold);

    }}

    .question-text {{

      font-family: 'DM Serif Display', serif;

      font-size: 1.05rem;

      color: var(--gold);

      line-height: 1.5;

      font-style: italic;

    }}

    .footer {{

      margin-top: 2rem;

      padding-top: 1.25rem;

      border-top: 1px solid var(--divider);

      display: flex;

      align-items: center;

      justify-content: space-between;

    }}

    .footer-label {{

      font-size: 10px;

      letter-spacing: 0.2em;

      text-transform: uppercase;

      color: rgba(255,255,255,0.25);

    }}

    @media (max-width: 480px) {{

      .card {{ padding: 1.75rem 1.5rem 1.5rem; }}

      body {{ padding: 1rem; }}

    }}

  </style>

</head>

<body>

  <div class="card">

    <div class="top-bar">

      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 80" class="avc-logo" aria-label="AVC">

        <g transform="translate(8,8)">

          <circle cx="32" cy="32" r="30" stroke="#60a5fa" stroke-width="1.5" fill="none" opacity="0.15"/>

          <circle cx="32" cy="32" r="22" stroke="#60a5fa" stroke-width="2" fill="none" opacity="0.35"/>

          <circle cx="32" cy="32" r="14" stroke="#60a5fa" stroke-width="2.5" fill="none" opacity="0.6"/>

          <line x1="24" y1="32" x2="44" y2="32" stroke="#93c5fd" stroke-width="3" stroke-linecap="round"/>

          <polyline points="38,26 44,32 38,38" stroke="#93c5fd" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/>

        </g>

        <line x1="82" y1="18" x2="82" y2="62" stroke="#334155" stroke-width="1"/>

        <text x="98" y="32" font-family="Inter,Arial,sans-serif" font-size="18" font-weight="800" letter-spacing="3" fill="#f1f5f9">ACCELERATED</text>

        <text x="98" y="52" font-family="Inter,Arial,sans-serif" font-size="18" font-weight="300" letter-spacing="3" fill="#60a5fa">VELOCITY</text>

        <text x="98" y="68" font-family="Inter,Arial,sans-serif" font-size="10" font-weight="400" letter-spacing="5.5" fill="#64748b">CONSULTING</text>

      </svg>

      <span class="date">{date}</span>

    </div>

    <div class="type-badge">{type_emoji} {type_label}</div>

    <h1>{headline}</h1>

    <div class="divider"></div>

    <p class="body-text">{body}</p>

    <div class="concept">

      <span class="concept-text">{concept}</span>

    </div>

    <div class="question-label">Today's Question</div>

    <div class="question-text">{question}</div>

    <div class="footer">

      <span class="footer-label">AVC One Thing — {date}</span>

      <span class="footer-label">acceleratedvelocity.com</span>

    </div>

  </div>

</body>

</html>'''

def build_html(candidate: dict, og_image_url: str) -> str:
    body_short = candidate["body"][:120].rstrip() + "..."
    return HTML_TEMPLATE.format(
        headline=candidate["headline"],
        body_short=body_short,
        og_image_url=og_image_url,
        date=TODAY,
        type_emoji=TYPE_EMOJI.get(candidate["type"], "🎯"),
        type_label=TYPE_LABEL.get(candidate["type"], candidate["type"]),
        body=candidate["body"],
        concept=candidate["concept"],
        question=candidate["question"],
    )

# ── Stage 4: Build OG image per candidate ─────────────────────────────────────
OG_W, OG_H = 1200, 630

def hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def wrap_text_pil(text: str, font, draw, max_width: int) -> list[str]:
    words = text.split()
    lines, line = [], []
    for word in words:
        test = " ".join(line + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > max_width and line:
            lines.append(" ".join(line))
            line = [word]
        else:
            line.append(word)
    if line:
        lines.append(" ".join(line))
    return lines

def build_og_image(candidate: dict, out_path: Path, fonts: dict) -> None:
    img = Image.new("RGB", (OG_W, OG_H), hex_to_rgb(BRAND["navy"]))
    draw = ImageDraw.Draw(img)

    f_serif_lg  = load_pil_font(fonts.get("serif"),         52)
    f_serif_md  = load_pil_font(fonts.get("serif"),         38)
    f_sans_sm   = load_pil_font(fonts.get("sans_regular"),  22)
    f_sans_xs   = load_pil_font(fonts.get("sans_regular"),  18)
    f_sans_bold = load_pil_font(fonts.get("sans_bold"),     16)

    gold_rgb  = hex_to_rgb(BRAND["gold"])
    white_rgb = hex_to_rgb(BRAND["white"])
    blue_rgb  = hex_to_rgb(BRAND["blue"])

    PAD = 72
    y = 58

    # AVC logo
    cx, cy, r = PAD + 22, y + 22, 20
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=(*blue_rgb, 38), width=2)
    draw.ellipse([cx-14, cy-14, cx+14, cy+14], outline=(*blue_rgb, 90), width=2)
    draw.ellipse([cx-8, cy-8, cx+8, cy+8], outline=(*blue_rgb, 153), width=2)
    draw.line([cx-6, cy, cx+8, cy], fill=hex_to_rgb(BRAND["blue_arrow"]), width=2)
    draw.line([cx+4, cy-5, cx+8, cy], fill=hex_to_rgb(BRAND["blue_arrow"]), width=2)
    draw.line([cx+4, cy+5, cx+8, cy], fill=hex_to_rgb(BRAND["blue_arrow"]), width=2)
    draw.line([PAD + 52, y + 6, PAD + 52, y + 38], fill=hex_to_rgb(BRAND["divider"]), width=1)

    f_logo_bold = load_pil_font(fonts.get("sans_bold"), 13)
    f_logo_thin = load_pil_font(fonts.get("sans_regular"), 13)
    draw.text((PAD + 62, y + 4),  "ACCELERATED", font=f_logo_bold, fill=white_rgb)
    draw.text((PAD + 62, y + 20), "VELOCITY",    font=f_logo_thin, fill=blue_rgb)
    draw.text((PAD + 62, y + 34), "CONSULTING",  font=f_logo_thin, fill=(100, 116, 139))
    y += 80

    # Type badge
    type_label = f"  {TYPE_EMOJI.get(candidate['type'], '')}  {TYPE_LABEL.get(candidate['type'], candidate['type']).upper()}  "
    bbox = draw.textbbox((0, 0), type_label, font=f_sans_bold)
    bw, bh = bbox[2] + 4, bbox[3] + 16
    draw.rounded_rectangle([PAD - 2, y - 2, PAD + bw, y + bh], radius=6,
                            fill=(*gold_rgb, 25), outline=(*gold_rgb, 77), width=1)
    draw.text((PAD + 2, y + 4), type_label, font=f_sans_bold, fill=gold_rgb)
    y += bh + 22

    # Headline
    max_w = OG_W - PAD * 2
    lines = wrap_text_pil(candidate["headline"], f_serif_lg, draw, max_w)
    f_headline = f_serif_md if len(lines) > 2 else f_serif_lg
    if len(lines) > 2:
        lines = wrap_text_pil(candidate["headline"], f_serif_md, draw, max_w)
    for line in lines[:3]:
        draw.text((PAD, y), line, font=f_headline, fill=white_rgb)
        bbox = draw.textbbox((PAD, y), line, font=f_headline)
        y += bbox[3] - bbox[1] + 8
    y += 14

    # Rule
    draw.line([PAD, y, OG_W - PAD, y], fill=(*white_rgb, 20), width=1)
    y += 22

    # Body
    body_short = candidate["body"].split(".")[0] + "."
    for line in wrap_text_pil(body_short, f_sans_sm, draw, max_w)[:2]:
        draw.text((PAD, y), line, font=f_sans_sm, fill=(*white_rgb, 178))
        y += 30
    y += 8

    # Implication
    draw.rectangle([PAD, y, PAD + 3, y + 60], fill=blue_rgb)
    for line in wrap_text_pil(candidate["concept"], f_sans_sm, draw, max_w - 22)[:2]:
        draw.text((PAD + 18, y), line, font=f_sans_sm, fill=(*white_rgb, 200))
        y += 28

    # Footer
    y_foot = OG_H - 42
    draw.line([PAD, y_foot, OG_W - PAD, y_foot], fill=(*white_rgb, 15), width=1)
    draw.text((PAD, y_foot + 12), f"AVC ONE THING  —  {TODAY.upper()}",
              font=f_sans_xs, fill=(*white_rgb, 100))
    draw.text((OG_W - PAD - 220, y_foot + 12), "ACCELERATED VELOCITY CONSULTING",
              font=f_sans_xs, fill=(*gold_rgb, 140))

    img.save(str(out_path), "PNG", optimize=True)

# ── Stage 5: Commit to repo ───────────────────────────────────────────────────
def commit_and_push() -> None:
    subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)
    subprocess.run(["git", "config", "user.name",  "GitHub Actions"],     check=True)
    subprocess.run(["git", "add", "docs/"],                               check=True)
    subprocess.run(["git", "add", "one_thing_candidates.json"],           check=True)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if result.returncode != 0:
        subprocess.run(["git", "commit", "-m", f"one thing: {TODAY_SLUG}"], check=True)
        subprocess.run(["git", "push"],                                      check=True)
        print("  ✅ Committed and pushed to GitHub Pages")
    else:
        print("  ℹ️  No changes to commit")

# ── Stage 6: Telegram delivery ────────────────────────────────────────────────
def send_telegram(chat_id: str, text: str) -> None:
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10
    ).raise_for_status()

def build_telegram_summary(candidates: list[dict]) -> str:
    lines = [f"🎯 ONE THING — {TODAY}\n4 candidates ready. Pick one URL → paste into iMessage to Mat.\n"]
    for c in candidates:
        emoji = TYPE_EMOJI.get(c["type"], "🎯")
        slug  = f"one-thing-{TODAY_SLUG}-{c['number']}"
        url   = f"{GITHUB_PAGES_URL}/{slug}.html"
        lines.append(f"{c['number']}. {emoji} {c['type']}")
        lines.append(f"{c['headline']}")
        lines.append(f"{url}\n")
    return "\n".join(lines)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    fonts      = get_fonts()
    signals    = fetch_signals()
    candidates = generate_candidates(signals)

    if not candidates:
        raise RuntimeError("No candidates parsed — check Claude output format")

    print("🎨 Building HTML pages and OG images...")
    for c in candidates:
        slug      = f"one-thing-{TODAY_SLUG}-{c['number']}"
        html_path = DOCS_DIR / f"{slug}.html"
        og_path   = DOCS_DIR / f"{slug}-og.png"
        og_url    = f"{GITHUB_PAGES_URL}/{slug}-og.png"

        build_og_image(c, og_path, fonts)
        html_path.write_text(build_html(c, og_url), encoding="utf-8")
        print(f"  ✅ {slug}")

    Path("one_thing_candidates.json").write_text(
        json.dumps({"date": TODAY, "date_slug": TODAY_SLUG,
                    "generated": datetime.utcnow().isoformat(),
                    "candidates": candidates}, indent=2)
    )

    commit_and_push()
    send_telegram(TELEGRAM_CHAT_ID, build_telegram_summary(candidates))
    print("\n✅ Done. 4 candidates live on GitHub Pages, URLs in your Telegram.")

if __name__ == "__main__":
    main()
