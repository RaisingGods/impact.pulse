"""
IMPACT PULSE Crawler — IMC IMPACT / Imaginarium Marketing Communications
Monitors Mastercard Foundation Nigeria programs across Nigerian media.
Runs every 120 minutes on Railway. Pushes results to GitHub Pages after each crawl.
SECURITY: Never upload this file to GitHub. API keys live in Railway Variables only.
"""

import os
import json
import base64
import logging
import hashlib
import requests
import feedparser
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from anthropic import Anthropic
from apscheduler.schedulers.blocking import BlockingScheduler

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("impact_pulse.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ── Environment Variables (set in Railway Variables panel) ────────────────────
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_KEY", "")
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO    = "RaisingGods/impact.pulse"          # your repo
RESULTS_FILE   = "impact_pulse_results.json"          # file in repo root
RESULTS_PATH   = "impact_pulse_results.json"          # same name locally

client = Anthropic(api_key=ANTHROPIC_KEY)

# ── 15 Mastercard Foundation Nigeria Programs ─────────────────────────────────
PROGRAMS = {
    "Young Africa Works":          ["Young Africa Works", "YAW Nigeria", "Mastercard Foundation jobs"],
    "Jobberman":                   ["Jobberman", "Jobberman Nigeria", "Jobberman soft skills"],
    "TAFTA":                       ["TAFTA Nigeria", "Traditional Arts Fashion Technology", "TAFTA fashion"],
    "WOFAN ICON 2":                ["WOFAN", "ICON 2 Nigeria", "Women Farmers Advancement Network"],
    "Babban Gona":                 ["Babban Gona", "Babban Gona farmers", "Babban Gona Nigeria"],
    "IITA I-Youth":                ["IITA I-Youth", "IITA youth agribusiness", "IITA Nigeria"],
    "Scholars Program":            ["Mastercard Foundation Scholars", "MCF Scholars Nigeria", "Scholars Program Africa"],
    "Project Juriya":              ["Project Juriya", "Juriya Nigeria", "Juriya women empowerment"],
    "Ethnocentrique Fashion Future": ["Ethnocentrique", "Fashion Future Nigeria", "Ethnocentrique Lagos"],
    "EDC":                         ["EDC Nigeria", "Enterprise Development Centre", "EDC Pan-Atlantic"],
    "FCMB Easylift":               ["FCMB Easylift", "Easylift Nigeria", "FCMB women entrepreneurs"],
    "Songhai Center":              ["Songhai Center Nigeria", "Songhai agricultural", "Songhai Mastercard"],
    "Christian Aid SEPTP":         ["Christian Aid SEPTP", "SEPTP Nigeria", "Christian Aid Nigeria economic"],
    "WISE Program":                ["WISE Program Nigeria", "Women in Science Education", "WISE Mastercard"],
    "TracTrac ISSAM":              ["TracTrac Nigeria", "ISSAM Nigeria", "TracTrac ISSAM monitoring"],
}

# ── Nigerian News RSS Feeds ───────────────────────────────────────────────────
RSS_FEEDS = [
    "https://punchng.com/feed/",
    "https://guardian.ng/feed/",
    "https://businessday.ng/feed/",
    "https://www.vanguardngr.com/feed/",
    "https://thenationonlineng.net/feed/",
    "https://dailytrust.com/feed/",
    "https://www.channelstv.com/feed/",
    "https://techcabal.com/feed/",
    "https://nairametrics.com/feed/",
    "https://www.premiumtimesng.com/feed/",
    "https://www.icirnigeria.org/feed/",
    "https://www.blueprint.ng/feed/",
]

# ── Seen articles cache (deduplication) ──────────────────────────────────────
seen_hashes: set = set()

def article_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

# ── Fetch full article text ───────────────────────────────────────────────────
def fetch_article_text(url: str) -> str:
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "IMCIMPACTPulse/1.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text() for p in paragraphs)
        return text[:3000]
    except Exception as e:
        log.warning(f"Could not fetch article text: {e}")
        return ""

# ── Claude sentiment analysis ─────────────────────────────────────────────────
def analyse_sentiment(title: str, text: str, program: str) -> dict:
    prompt = f"""You are a Nigerian media analyst for IMC IMPACT, a development communications agency in Lagos.

Analyse this article about the {program} program and return ONLY a JSON object with these exact keys:
- sentiment: one of "positive", "negative", "neutral", "mixed"
- sentiment_score: a number from -1.0 (very negative) to 1.0 (very positive)
- summary: one sentence (max 25 words) summarising the article's stance on the program
- key_theme: one of "employment", "agriculture", "education", "women empowerment", "entrepreneurship", "policy", "technology", "health", "other"
- language_note: note if article contains Nigerian Pidgin, Hausa, or Yoruba phrases (or write "Standard English")

Article title: {title}

Article text: {text[:1500]}

Return ONLY the JSON object, no explanation."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        log.warning(f"Sentiment analysis failed: {e}")
        return {
            "sentiment": "neutral",
            "sentiment_score": 0.0,
            "summary": "Analysis unavailable.",
            "key_theme": "other",
            "language_note": "Standard English"
        }

# ── Push results JSON to GitHub ───────────────────────────────────────────────
def push_to_github(results: dict):
    if not GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN not set — skipping GitHub push")
        return

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{RESULTS_FILE}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Get current file SHA (needed for update)
    sha = None
    try:
        r = requests.get(api_url, headers=headers, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception as e:
        log.warning(f"Could not fetch existing file SHA: {e}")

    # Encode content
    content_bytes = json.dumps(results, ensure_ascii=False, indent=2).encode("utf-8")
    content_b64 = base64.b64encode(content_bytes).decode("utf-8")

    payload = {
        "message": f"Auto-update: crawl results {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "content": content_b64,
    }
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(api_url, headers=headers, json=payload, timeout=15)
        if r.status_code in (200, 201):
            log.info("✅ Results pushed to GitHub successfully")
        else:
            log.error(f"GitHub push failed: {r.status_code} — {r.text[:200]}")
    except Exception as e:
        log.error(f"GitHub push error: {e}")

# ── Main crawl function ───────────────────────────────────────────────────────
def run_crawl():
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info("IMPACT PULSE — Starting crawl cycle")
    log.info(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    # Load existing results or start fresh
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH, "r", encoding="utf-8") as f:
            results = json.load(f)
    else:
        results = {
            "last_updated": "",
            "total_articles": 0,
            "articles": [],
            "program_summary": {},
            "sentiment_overview": {
                "positive": 0, "negative": 0, "neutral": 0, "mixed": 0
            }
        }

    new_count = 0

    for feed_url in RSS_FEEDS:
        try:
            log.info(f"Checking feed: {feed_url}")
            feed = feedparser.parse(feed_url)

            for entry in feed.entries[:20]:  # check latest 20 per feed
                url   = getattr(entry, "link", "")
                title = getattr(entry, "title", "No title")
                published = getattr(entry, "published", str(datetime.now(timezone.utc).date()))

                if not url:
                    continue

                h = article_hash(url)
                if h in seen_hashes:
                    continue

                # Check if any program keyword appears in title or summary
                matched_program = None
                entry_text = f"{title} {getattr(entry, 'summary', '')}".lower()

                for program, keywords in PROGRAMS.items():
                    if any(kw.lower() in entry_text for kw in keywords):
                        matched_program = program
                        break

                if not matched_program:
                    continue

                # Fetch full text and analyse
                log.info(f"  ✓ Match: [{matched_program}] {title[:60]}")
                article_text = fetch_article_text(url)
                sentiment    = analyse_sentiment(title, article_text, matched_program)

                article = {
                    "id":             h,
                    "program":        matched_program,
                    "title":          title,
                    "url":            url,
                    "source":         feed.feed.get("title", feed_url),
                    "published":      published,
                    "crawled_at":     datetime.now(timezone.utc).isoformat(),
                    "sentiment":      sentiment.get("sentiment", "neutral"),
                    "sentiment_score": sentiment.get("sentiment_score", 0.0),
                    "summary":        sentiment.get("summary", ""),
                    "key_theme":      sentiment.get("key_theme", "other"),
                    "language_note":  sentiment.get("language_note", "Standard English"),
                }

                results["articles"].insert(0, article)  # newest first
                seen_hashes.add(h)
                new_count += 1

                # Update sentiment overview
                s = article["sentiment"]
                results["sentiment_overview"][s] = results["sentiment_overview"].get(s, 0) + 1

        except Exception as e:
            log.error(f"Feed error ({feed_url}): {e}")

    # Keep only latest 500 articles to avoid file bloat
    results["articles"] = results["articles"][:500]

    # Rebuild program summary
    program_summary = {}
    for art in results["articles"]:
        p = art["program"]
        if p not in program_summary:
            program_summary[p] = {"count": 0, "positive": 0, "negative": 0, "neutral": 0, "mixed": 0, "last_article": ""}
        program_summary[p]["count"] += 1
        program_summary[p][art["sentiment"]] += 1
        if not program_summary[p]["last_article"]:
            program_summary[p]["last_article"] = art["title"]

    results["program_summary"]  = program_summary
    results["total_articles"]   = len(results["articles"])
    results["last_updated"]     = datetime.now(timezone.utc).isoformat()

    # Save locally
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    log.info(f"Crawl complete — {new_count} new articles found")
    log.info(f"Total articles in database: {results['total_articles']}")

    # Push to GitHub
    push_to_github(results)

    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

# ── Scheduler ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("IMPACT PULSE Crawler starting up — IMC IMPACT / Imaginarium Marketing Communications")
    log.info("Monitoring 15 Mastercard Foundation Nigeria programs")

    # Run immediately on startup
    run_crawl()

    # Then every 120 minutes
    scheduler = BlockingScheduler(timezone="Africa/Lagos")
    scheduler.add_job(run_crawl, "interval", minutes=120)
    log.info("Scheduler active — next crawl in 120 minutes")
    scheduler.start()
