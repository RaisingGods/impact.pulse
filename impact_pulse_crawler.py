"""
IMPACT PULSE Crawler — IMC IMPACT / Imaginarium Marketing Communications
Monitors Mastercard Foundation Nigeria programs across Nigerian media.
Runs every 120 minutes on Railway. Pushes results to GitHub after each crawl.
"""

import os, json, base64, logging, hashlib, requests, feedparser
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from anthropic import Anthropic
from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("impact_pulse.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_KEY", "")
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO    = "RaisingGods/impact.pulse"
GITHUB_BRANCH  = "main"
RESULTS_FILE   = "impact_pulse_results.json"

client = Anthropic(api_key=ANTHROPIC_KEY)

# ── Programs with BROAD keyword sets ─────────────────────────────────────────
# Using short, common words that will actually appear in Nigerian news headlines
PROGRAMS = {
    "Young Africa Works": [
        "Young Africa Works", "Mastercard Foundation", "youth employment",
        "job creation Nigeria", "YAW Nigeria", "Africa Works"
    ],
    "Jobberman": [
        "Jobberman", "soft skills training", "job placement Nigeria",
        "employment Nigeria", "labour market Nigeria", "jobs Nigeria"
    ],
    "TAFTA": [
        "TAFTA", "fashion training Nigeria", "textile Nigeria",
        "fashion school Nigeria", "Traditional Arts Fashion"
    ],
    "WOFAN ICON 2": [
        "WOFAN", "women farmers Nigeria", "ICON 2",
        "Women Farmers Advancement", "female farmers Nigeria"
    ],
    "Babban Gona": [
        "Babban Gona", "smallholder farmers", "agricultural cooperative Nigeria",
        "farmer cooperative Nigeria", "agric cooperative"
    ],
    "IITA I-Youth": [
        "IITA", "youth agribusiness", "agribusiness Nigeria",
        "International Institute Tropical Agriculture", "I-Youth"
    ],
    "Scholars Program": [
        "Mastercard Foundation Scholars", "MCF Scholars", "Mastercard scholarship",
        "scholarship Nigeria", "university scholarship Africa"
    ],
    "Project Juriya": [
        "Project Juriya", "Juriya", "women empowerment northern Nigeria",
        "northern Nigeria women", "Kaduna women empowerment"
    ],
    "Ethnocentrique Fashion Future": [
        "Ethnocentrique", "Fashion Future", "African fashion",
        "fashion entrepreneur Nigeria", "Aba fashion", "fashion business Nigeria"
    ],
    "EDC": [
        "Enterprise Development Centre", "EDC Nigeria", "Pan-Atlantic University",
        "SME Nigeria", "small business Nigeria", "entrepreneurship Nigeria"
    ],
    "FCMB Easylift": [
        "FCMB Easylift", "Easylift", "FCMB women", "FCMB loan",
        "women entrepreneur loan", "FCMB Nigeria"
    ],
    "Songhai Center": [
        "Songhai", "agribusiness training", "Songhai Nigeria",
        "agricultural training Nigeria", "farm training Nigeria"
    ],
    "Christian Aid SEPTP": [
        "Christian Aid Nigeria", "SEPTP", "Christian Aid",
        "economic empowerment Nigeria", "poverty Nigeria"
    ],
    "WISE Program": [
        "WISE Program", "women science Nigeria", "girls education Nigeria",
        "STEM Nigeria women", "female education Nigeria"
    ],
    "TracTrac ISSAM": [
        "TracTrac", "ISSAM Nigeria", "social accountability Nigeria",
        "program monitoring Nigeria", "community monitoring"
    ],
}

# ── BROAD catch-all keywords — any article about Nigerian development ──────────
# These ensure we always capture relevant content even if program names aren't mentioned
BROAD_KEYWORDS = [
    "Mastercard Foundation Nigeria",
    "youth employment Nigeria",
    "women empowerment Nigeria",
    "agricultural development Nigeria",
    "skills training Nigeria",
    "entrepreneurship Nigeria",
    "development program Nigeria",
    "NGO Nigeria",
    "foundation Nigeria program",
]

RSS_FEEDS = [
    ("Punch Newspapers",     "https://punchng.com/feed/"),
    ("Premium Times",        "https://www.premiumtimesng.com/feed/"),
    ("The Guardian NG",      "https://guardian.ng/feed/"),
    ("Vanguard",             "https://www.vanguardngr.com/feed/"),
    ("BusinessDay",          "https://businessday.ng/feed/"),
    ("The Nation",           "https://thenationonlineng.net/feed/"),
    ("Daily Trust",          "https://dailytrust.com/feed/"),
    ("Channels TV",          "https://www.channelstv.com/feed/"),
    ("TechCabal",            "https://techcabal.com/feed/"),
    ("Nairametrics",         "https://nairametrics.com/feed/"),
    ("The Cable",            "https://www.thecable.ng/feed"),
    ("Leadership NG",        "https://leadership.ng/feed/"),
]

seen_hashes: set = set()

def article_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def fetch_article_text(url: str) -> str:
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "IMCIMPACTPulse/1.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        return " ".join(p.get_text() for p in soup.find_all("p"))[:3000]
    except Exception as e:
        log.warning(f"Could not fetch article text: {e}")
        return ""

def match_program(text: str) -> str | None:
    """Return matched program name or None."""
    text_lower = text.lower()
    for program, keywords in PROGRAMS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            return program
    # Check broad keywords — assign to "General Coverage"
    if any(kw.lower() in text_lower for kw in BROAD_KEYWORDS):
        return "General Coverage"
    return None

def analyse_sentiment(title: str, text: str, program: str) -> dict:
    prompt = f"""You are a Nigerian media analyst for IMC IMPACT, a development communications agency in Lagos.

Analyse this article about {program} and return ONLY a JSON object:
- sentiment: "positive", "negative", "neutral", or "mixed"
- sentiment_score: number from -1.0 to 1.0
- summary: one sentence max 25 words on the article's stance
- key_theme: one of "employment", "agriculture", "education", "women empowerment", "entrepreneurship", "policy", "technology", "health", "other"
- language_note: note any Nigerian Pidgin, Hausa, or Yoruba (or write "Standard English")
- speaker_type: one of "participant", "journalist", "government", "influencer", "partner", "unknown"

Title: {title}
Text: {text[:1500]}

Return ONLY the JSON object, nothing else."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip().replace("```json","").replace("```","").strip()
        return json.loads(raw)
    except Exception as e:
        log.warning(f"Sentiment analysis failed: {e}")
        return {
            "sentiment": "neutral", "sentiment_score": 0.0,
            "summary": "Analysis unavailable.", "key_theme": "other",
            "language_note": "Standard English", "speaker_type": "unknown"
        }

def push_to_github(results: dict):
    if not GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN not set — skipping GitHub push")
        return

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{RESULTS_FILE}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    sha = None
    try:
        r = requests.get(api_url, headers=headers, params={"ref": GITHUB_BRANCH}, timeout=10)
        log.info(f"SHA fetch status: {r.status_code}")
        if r.status_code == 200:
            sha = r.json().get("sha")
            log.info(f"Existing SHA: {sha[:8]}...")
        elif r.status_code == 404:
            log.info("File does not exist yet — will create it")
        else:
            log.warning(f"SHA fetch error: {r.text[:200]}")
    except Exception as e:
        log.warning(f"SHA fetch exception: {e}")

    content_b64 = base64.b64encode(
        json.dumps(results, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("utf-8")

    payload = {
        "message": f"Auto-update crawl results {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "content": content_b64,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(api_url, headers=headers, json=payload, timeout=20)
        if r.status_code in (200, 201):
            log.info("✅ Results pushed to GitHub successfully")
        else:
            log.error(f"GitHub push failed: {r.status_code} — {r.text[:300]}")
    except Exception as e:
        log.error(f"GitHub push exception: {e}")

def run_crawl():
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info(f"IMPACT PULSE — Crawl cycle starting {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            results = json.load(f)
        for art in results.get("articles", []):
            seen_hashes.add(art.get("id", ""))
    else:
        results = {
            "last_updated": "",
            "total_articles": 0,
            "articles": [],
            "program_summary": {},
            "sentiment_overview": {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}
        }

    new_count = 0

    for feed_name, feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            entries = feed.entries[:30]
            log.info(f"  {feed_name}: {len(entries)} entries")

            for entry in entries:
                url   = getattr(entry, "link", "")
                title = getattr(entry, "title", "No title")
                published = getattr(entry, "published", str(datetime.now(timezone.utc).date()))

                if not url:
                    continue

                h = article_hash(url)
                if h in seen_hashes:
                    continue

                entry_text = f"{title} {getattr(entry, 'summary', '')}"
                matched_program = match_program(entry_text)

                if not matched_program:
                    continue

                log.info(f"    ✓ [{matched_program}] {title[:70]}")
                article_text = fetch_article_text(url)

                # Re-check with full text if only broad match
                if matched_program == "General Coverage":
                    full_match = match_program(article_text)
                    if full_match and full_match != "General Coverage":
                        matched_program = full_match

                sentiment = analyse_sentiment(title, article_text, matched_program)

                article = {
                    "id":              h,
                    "program":         matched_program,
                    "title":           title,
                    "url":             url,
                    "source":          feed_name,
                    "published":       published,
                    "crawled_at":      datetime.now(timezone.utc).isoformat(),
                    "sentiment":       sentiment.get("sentiment", "neutral"),
                    "sentiment_score": sentiment.get("sentiment_score", 0.0),
                    "summary":         sentiment.get("summary", ""),
                    "key_theme":       sentiment.get("key_theme", "other"),
                    "language_note":   sentiment.get("language_note", "Standard English"),
                    "speaker_type":    sentiment.get("speaker_type", "unknown"),
                }

                results["articles"].insert(0, article)
                seen_hashes.add(h)
                new_count += 1

                s = article["sentiment"]
                results["sentiment_overview"][s] = results["sentiment_overview"].get(s, 0) + 1

        except Exception as e:
            log.error(f"Feed error ({feed_name}): {e}")

    results["articles"] = results["articles"][:500]

    program_summary = {}
    for art in results["articles"]:
        p = art["program"]
        if p not in program_summary:
            program_summary[p] = {"count": 0, "positive": 0, "negative": 0, "neutral": 0, "mixed": 0, "last_article": ""}
        program_summary[p]["count"] += 1
        program_summary[p][art["sentiment"]] = program_summary[p].get(art["sentiment"], 0) + 1
        if not program_summary[p]["last_article"]:
            program_summary[p]["last_article"] = art["title"]

    results["program_summary"] = program_summary
    results["total_articles"]  = len(results["articles"])
    results["last_updated"]    = datetime.now(timezone.utc).isoformat()

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    log.info(f"Crawl complete — {new_count} new articles found")
    log.info(f"Total in database: {results['total_articles']}")
    push_to_github(results)
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

if __name__ == "__main__":
    log.info("IMPACT PULSE — IMC IMPACT / Imaginarium Marketing Communications")
    log.info("Monitoring 15 Mastercard Foundation Nigeria programs")
    run_crawl()
    scheduler = BlockingScheduler(timezone="Africa/Lagos")
    scheduler.add_job(run_crawl, "interval", minutes=120)
    log.info("Scheduler active — next crawl in 120 minutes")
    scheduler.start()
