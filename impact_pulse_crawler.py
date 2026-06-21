"""
IMPACT PULSE Crawler v2 — IMC IMPACT / Imaginarium Marketing Communications
Uses NewsAPI.org + social media monitoring for 15 Mastercard Foundation Nigeria programs.
Runs every 120 minutes on Railway. Pushes results to GitHub after each crawl.
"""

import os, json, base64, logging, hashlib, requests, time
from datetime import datetime, timezone, timedelta
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
NEWS_API_KEY   = os.environ.get("NEWS_API_KEY", "")
GITHUB_REPO    = "RaisingGods/impact.pulse"
GITHUB_BRANCH  = "main"
RESULTS_FILE   = "impact_pulse_results.json"

client = Anthropic(api_key=ANTHROPIC_KEY)

# ── NewsAPI queries — broad enough to catch real coverage ─────────────────────
# Strategy: use SHORT, common terms. NewsAPI free tier works best with 1-2 keywords.
PROGRAM_QUERIES = {
    "Young Africa Works":            ["Young Africa Works", "Mastercard Foundation youth Nigeria", "YAW Nigeria employment"],
    "Jobberman":                     ["Jobberman Nigeria", "Jobberman skills", "Jobberman jobs"],
    "TAFTA":                         ["TAFTA Nigeria", "fashion training Nigeria", "TAFTA fashion"],
    "WOFAN ICON 2":                  ["WOFAN Nigeria", "women farmers Nigeria", "ICON 2 Nigeria"],
    "Babban Gona":                   ["Babban Gona", "Babban Gona farmers"],
    "IITA I-Youth":                  ["IITA Nigeria", "IITA youth agribusiness"],
    "Scholars Program":              ["Mastercard Foundation Scholars", "MCF Scholars Nigeria", "Mastercard scholarship Africa"],
    "Project Juriya":                ["Project Juriya", "Juriya Nigeria women"],
    "Ethnocentrique Fashion Future": ["Ethnocentrique Nigeria", "Fashion Future Nigeria"],
    "EDC":                           ["Enterprise Development Centre Nigeria", "EDC Pan-Atlantic Nigeria"],
    "FCMB Easylift":                 ["FCMB Easylift", "FCMB women entrepreneurs Nigeria"],
    "Songhai Center":                ["Songhai Nigeria", "Songhai agricultural Nigeria"],
    "Christian Aid SEPTP":           ["Christian Aid Nigeria", "SEPTP Nigeria"],
    "WISE Program":                  ["WISE Program Nigeria", "women STEM Nigeria"],
    "TracTrac ISSAM":                ["TracTrac Nigeria", "ISSAM Nigeria"],
}

# ── Broad catch-all queries ───────────────────────────────────────────────────
BROAD_QUERIES = [
    "Mastercard Foundation Nigeria",
    "youth employment Nigeria 2026",
    "women empowerment Nigeria development",
    "agricultural development Nigeria NGO",
    "skills training Nigeria foundation",
    "Nigeria development program 2026",
]

# ── Social media simulation via NewsAPI ──────────────────────────────────────
# NewsAPI indexes social media content through news aggregators
# These queries target social/community coverage
SOCIAL_QUERIES = [
    ("Twitter/X Nigeria",   "Nigeria youth employment Twitter site:twitter.com OR site:x.com"),
    ("Community Voice",     "Nigeria farming community empowerment 2026"),
    ("Youth Voice Nigeria", "Nigeria graduate jobs skills 2026 youth"),
    ("Women Voice Nigeria", "Nigeria women entrepreneur business 2026"),
]

seen_hashes: set = set()

def article_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def fetch_newsapi(query: str, days_back: int = 7, page_size: int = 10) -> list:
    if not NEWS_API_KEY:
        log.warning("NEWS_API_KEY not set")
        return []
    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime('%Y-%m-%d')
    params = {
        "q":        query,
        "from":     from_date,
        "language": "en",
        "sortBy":   "publishedAt",
        "pageSize": page_size,
        "apiKey":   NEWS_API_KEY,
    }
    try:
        r = requests.get("https://newsapi.org/v2/everything", params=params, timeout=15)
        if r.status_code == 200:
            articles = r.json().get("articles", [])
            log.info(f"  NewsAPI [{query[:45]}]: {len(articles)} articles")
            return articles
        elif r.status_code == 429:
            log.warning("NewsAPI rate limit — pausing 60s")
            time.sleep(60)
            return []
        else:
            log.warning(f"NewsAPI {r.status_code}: {r.text[:100]}")
            return []
    except Exception as e:
        log.error(f"NewsAPI error: {e}")
        return []

def analyse_sentiment(title: str, description: str, program: str) -> dict:
    prompt = f"""You are a Nigerian media analyst for IMC IMPACT, a development communications agency in Lagos.

Analyse this article about {program} and return ONLY a valid JSON object:
- sentiment: "positive", "negative", "neutral", or "mixed"
- sentiment_score: number from -1.0 to 1.0
- summary: one sentence max 25 words on the article's stance
- key_theme: one of "employment", "agriculture", "education", "women empowerment", "entrepreneurship", "policy", "technology", "health", "other"
- language_note: "Standard English" or note Nigerian Pidgin/Hausa/Yoruba
- speaker_type: "participant", "journalist", "government", "influencer", "partner", or "unknown"
- media_type: "news", "social", "blog", "research", "press release", or "other"

Title: {title}
Content: {description[:600]}

Return ONLY the JSON."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip().replace("```json","").replace("```","").strip()
        return json.loads(raw)
    except Exception as e:
        log.warning(f"Sentiment error: {e}")
        return {
            "sentiment": "neutral", "sentiment_score": 0.0,
            "summary": "Analysis unavailable.", "key_theme": "other",
            "language_note": "Standard English", "speaker_type": "unknown",
            "media_type": "news"
        }

def process_articles(raw_articles: list, program: str) -> list:
    """Process a list of raw NewsAPI articles into IMPACT PULSE format."""
    processed = []
    for item in raw_articles:
        url   = item.get("url", "")
        title = item.get("title", "") or ""
        desc  = item.get("description", "") or ""
        content = item.get("content", "") or ""

        if not url or url == "https://removed.com":
            continue
        if "[Removed]" in title or not title.strip():
            continue

        h = article_hash(url)
        if h in seen_hashes:
            continue

        log.info(f"  ✓ [{program}] {title[:70]}")
        full_text = f"{desc} {content}"
        sentiment = analyse_sentiment(title, full_text, program)

        published = item.get("publishedAt", datetime.now(timezone.utc).isoformat())
        source    = item.get("source", {}).get("name", "Unknown")

        article = {
            "id":              h,
            "program":         program,
            "title":           title,
            "url":             url,
            "source":          source,
            "published":       published,
            "crawled_at":      datetime.now(timezone.utc).isoformat(),
            "sentiment":       sentiment.get("sentiment", "neutral"),
            "sentiment_score": sentiment.get("sentiment_score", 0.0),
            "summary":         sentiment.get("summary", ""),
            "key_theme":       sentiment.get("key_theme", "other"),
            "language_note":   sentiment.get("language_note", "Standard English"),
            "speaker_type":    sentiment.get("speaker_type", "unknown"),
            "media_type":      sentiment.get("media_type", "news"),
        }

        seen_hashes.add(h)
        processed.append(article)

    return processed

def push_to_github(results: dict):
    if not GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN not set — skipping")
        return

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{RESULTS_FILE}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    content_b64 = base64.b64encode(
        json.dumps(results, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("utf-8")

    sha = None
    try:
        r = requests.get(api_url, headers=headers, params={"ref": GITHUB_BRANCH}, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
            log.info(f"Fresh SHA: {sha[:8]}...")
    except Exception as e:
        log.warning(f"SHA error: {e}")

    payload = {
        "message": f"Auto-update {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "content": content_b64,
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    for attempt in range(2):
        try:
            r = requests.put(api_url, headers=headers, json=payload, timeout=20)
            if r.status_code in (200, 201):
                log.info("✅ Results pushed to GitHub successfully")
                return
            elif r.status_code == 409 and attempt == 0:
                log.warning("409 — re-fetching SHA")
                r2 = requests.get(api_url, headers=headers, params={"ref": GITHUB_BRANCH}, timeout=10)
                if r2.status_code == 200:
                    payload["sha"] = r2.json().get("sha")
            else:
                log.error(f"Push failed: {r.status_code} — {r.text[:200]}")
        except Exception as e:
            log.error(f"Push error: {e}")

def run_crawl():
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info(f"IMPACT PULSE — Crawl starting {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    if not NEWS_API_KEY:
        log.error("NEWS_API_KEY not set — cannot crawl")
        return

    # Load existing results
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
            "sentiment_overview": {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0},
            "social_mentions": []
        }

    new_count  = 0
    api_calls  = 0

    # ── Per-program queries (multiple queries per program) ────────────────────
    for program, queries in PROGRAM_QUERIES.items():
        if api_calls >= 80:
            log.warning("Approaching daily API limit — stopping program queries")
            break
        log.info(f"Searching: {program}")
        for query in queries:
            if api_calls >= 80:
                break
            raw = fetch_newsapi(query, days_back=7, page_size=5)
            api_calls += 1
            time.sleep(0.3)
            processed = process_articles(raw, program)
            for art in processed:
                results["articles"].insert(0, art)
                results["sentiment_overview"][art["sentiment"]] = \
                    results["sentiment_overview"].get(art["sentiment"], 0) + 1
                new_count += 1

    # ── Broad queries ─────────────────────────────────────────────────────────
    log.info("Running broad coverage queries...")
    for query in BROAD_QUERIES:
        if api_calls >= 90:
            break
        raw = fetch_newsapi(query, days_back=7, page_size=10)
        api_calls += 1
        time.sleep(0.3)
        processed = process_articles(raw, "General Coverage")
        for art in processed:
            results["articles"].insert(0, art)
            results["sentiment_overview"][art["sentiment"]] = \
                results["sentiment_overview"].get(art["sentiment"], 0) + 1
            new_count += 1

    # ── Social/community queries ──────────────────────────────────────────────
    log.info("Running social media queries...")
    for source_name, query in SOCIAL_QUERIES:
        if api_calls >= 95:
            break
        raw = fetch_newsapi(query, days_back=3, page_size=5)
        api_calls += 1
        time.sleep(0.3)
        for item in raw:
            url   = item.get("url", "")
            title = item.get("title", "") or ""
            if not url or "[Removed]" in title:
                continue
            h = article_hash(url)
            if h in seen_hashes:
                continue
            desc = item.get("description", "") or ""
            sentiment = analyse_sentiment(title, desc, "Social Media Monitoring")
            social_item = {
                "id":          h,
                "program":     "Social Media",
                "title":       title,
                "url":         url,
                "source":      source_name,
                "published":   item.get("publishedAt", ""),
                "crawled_at":  datetime.now(timezone.utc).isoformat(),
                "sentiment":   sentiment.get("sentiment", "neutral"),
                "summary":     sentiment.get("summary", ""),
                "key_theme":   sentiment.get("key_theme", "other"),
                "speaker_type": sentiment.get("speaker_type", "unknown"),
                "media_type":  "social",
            }
            results["articles"].insert(0, social_item)
            seen_hashes.add(h)
            new_count += 1

    # ── Finalise ──────────────────────────────────────────────────────────────
    results["articles"]       = results["articles"][:500]
    results["total_articles"] = len(results["articles"])
    results["last_updated"]   = datetime.now(timezone.utc).isoformat()

    program_summary = {}
    for art in results["articles"]:
        p = art["program"]
        if p not in program_summary:
            program_summary[p] = {
                "count": 0, "positive": 0, "negative": 0,
                "neutral": 0, "mixed": 0, "last_article": ""
            }
        program_summary[p]["count"] += 1
        program_summary[p][art["sentiment"]] = program_summary[p].get(art["sentiment"], 0) + 1
        if not program_summary[p]["last_article"]:
            program_summary[p]["last_article"] = art["title"]

    results["program_summary"] = program_summary

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    log.info(f"Crawl complete — {new_count} new articles found")
    log.info(f"Total in database: {results['total_articles']}")
    log.info(f"API calls this cycle: {api_calls}/100")
    push_to_github(results)
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

if __name__ == "__main__":
    log.info("IMPACT PULSE v2 — IMC IMPACT / Imaginarium Marketing Communications")
    log.info("Monitoring 15 Mastercard Foundation Nigeria programs")
    log.info("Sources: NewsAPI + Social Media queries")
    run_crawl()
    scheduler = BlockingScheduler(timezone="Africa/Lagos")
    scheduler.add_job(run_crawl, "interval", minutes=120)
    log.info("Scheduler active — next crawl in 120 minutes")
    scheduler.start()
