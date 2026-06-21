"""
IMPACT PULSE Crawler — IMC IMPACT / Imaginarium Marketing Communications
Uses NewsAPI.org to monitor 15 Mastercard Foundation Nigeria programs.
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

# ── 15 Programs with NewsAPI search queries ───────────────────────────────────
PROGRAM_QUERIES = {
    "Young Africa Works":              "Young Africa Works Nigeria OR Mastercard Foundation Nigeria youth",
    "Jobberman":                       "Jobberman Nigeria jobs OR Jobberman skills training",
    "TAFTA":                           "TAFTA Nigeria fashion OR Traditional Arts Fashion Technology",
    "WOFAN ICON 2":                    "WOFAN Nigeria women farmers OR ICON 2 Nigeria",
    "Babban Gona":                     "Babban Gona Nigeria farmers",
    "IITA I-Youth":                    "IITA Nigeria youth agribusiness OR IITA I-Youth",
    "Scholars Program":                "Mastercard Foundation Scholars Nigeria OR MCF Scholars",
    "Project Juriya":                  "Project Juriya Nigeria OR Juriya women empowerment",
    "Ethnocentrique Fashion Future":   "Ethnocentrique Nigeria fashion OR Fashion Future Nigeria",
    "EDC":                             "Enterprise Development Centre Nigeria OR EDC Pan-Atlantic",
    "FCMB Easylift":                   "FCMB Easylift Nigeria OR FCMB women entrepreneurs",
    "Songhai Center":                  "Songhai Center Nigeria agribusiness OR Songhai agricultural",
    "Christian Aid SEPTP":             "Christian Aid Nigeria SEPTP OR Christian Aid economic empowerment",
    "WISE Program":                    "WISE Program Nigeria women science OR girls STEM Nigeria",
    "TracTrac ISSAM":                  "TracTrac Nigeria OR ISSAM Nigeria monitoring",
}

# ── Broad fallback query to catch general coverage ────────────────────────────
BROAD_QUERY = "Mastercard Foundation Nigeria OR youth employment Nigeria OR women empowerment Nigeria development"

seen_hashes: set = set()

def article_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def fetch_newsapi(query: str, days_back: int = 3) -> list:
    """Fetch articles from NewsAPI for a given query."""
    if not NEWS_API_KEY:
        log.warning("NEWS_API_KEY not set")
        return []
    
    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime('%Y-%m-%d')
    
    url = "https://newsapi.org/v2/everything"
    params = {
        "q":        query,
        "from":     from_date,
        "language": "en",
        "sortBy":   "publishedAt",
        "pageSize": 20,
        "apiKey":   NEWS_API_KEY,
    }
    
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            articles = data.get("articles", [])
            log.info(f"  NewsAPI returned {len(articles)} articles for: {query[:50]}")
            return articles
        elif r.status_code == 426:
            log.warning("NewsAPI requires upgrade for this query — using free tier limits")
            return []
        else:
            log.warning(f"NewsAPI error {r.status_code}: {r.text[:100]}")
            return []
    except Exception as e:
        log.error(f"NewsAPI fetch error: {e}")
        return []

def analyse_sentiment(title: str, description: str, program: str) -> dict:
    prompt = f"""You are a Nigerian media analyst for IMC IMPACT, a development communications agency in Lagos.

Analyse this article about {program} and return ONLY a valid JSON object with these exact keys:
- sentiment: one of "positive", "negative", "neutral", "mixed"
- sentiment_score: number from -1.0 to 1.0
- summary: one sentence max 25 words describing the article's stance on the program
- key_theme: one of "employment", "agriculture", "education", "women empowerment", "entrepreneurship", "policy", "technology", "health", "other"
- language_note: "Standard English" or note any Nigerian Pidgin/Hausa/Yoruba
- speaker_type: one of "participant", "journalist", "government", "influencer", "partner", "unknown"

Title: {title}
Description: {description[:800]}

Return ONLY the JSON object."""

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

    content_b64 = base64.b64encode(
        json.dumps(results, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("utf-8")

    # Always fetch fresh SHA immediately before PUT
    sha = None
    try:
        r = requests.get(api_url, headers=headers, params={"ref": GITHUB_BRANCH}, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
            log.info(f"Fresh SHA: {sha[:8]}...")
        elif r.status_code == 404:
            log.info("File does not exist yet — creating fresh")
    except Exception as e:
        log.warning(f"SHA fetch error: {e}")

    payload = {
        "message": f"Auto-update crawl results {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "content": content_b64,
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    # Retry once on 409
    for attempt in range(2):
        try:
            r = requests.put(api_url, headers=headers, json=payload, timeout=20)
            if r.status_code in (200, 201):
                log.info("✅ Results pushed to GitHub successfully")
                return
            elif r.status_code == 409 and attempt == 0:
                log.warning("409 conflict — re-fetching SHA and retrying")
                r2 = requests.get(api_url, headers=headers, params={"ref": GITHUB_BRANCH}, timeout=10)
                if r2.status_code == 200:
                    payload["sha"] = r2.json().get("sha")
            else:
                log.error(f"GitHub push failed: {r.status_code} — {r.text[:200]}")
        except Exception as e:
            log.error(f"GitHub push error: {e}")

def run_crawl():
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info(f"IMPACT PULSE — Crawl starting {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    if not NEWS_API_KEY:
        log.error("NEWS_API_KEY not set — cannot crawl. Add it to Railway Variables.")
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
            "sentiment_overview": {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}
        }

    new_count = 0
    api_calls = 0

    # ── Query each program ────────────────────────────────────────────────────
    for program, query in PROGRAM_QUERIES.items():
        if api_calls >= 90:  # Stay within free tier limit
            log.warning("Approaching NewsAPI daily limit — stopping early")
            break

        log.info(f"Searching: {program}")
        articles = fetch_newsapi(query)
        api_calls += 1
        time.sleep(0.5)  # Be polite to the API

        for item in articles:
            url   = item.get("url", "")
            title = item.get("title", "")
            desc  = item.get("description", "") or ""

            if not url or url == "https://removed.com":
                continue
            if "[Removed]" in title:
                continue

            h = article_hash(url)
            if h in seen_hashes:
                continue

            log.info(f"  ✓ [{program}] {title[:70]}")
            sentiment = analyse_sentiment(title, desc, program)

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
            }

            results["articles"].insert(0, article)
            seen_hashes.add(h)
            new_count += 1

            s = article["sentiment"]
            results["sentiment_overview"][s] = results["sentiment_overview"].get(s, 0) + 1

    # ── Broad fallback query ──────────────────────────────────────────────────
    if api_calls < 90:
        log.info("Running broad fallback query...")
        broad_articles = fetch_newsapi(BROAD_QUERY)
        api_calls += 1

        for item in broad_articles:
            url   = item.get("url", "")
            title = item.get("title", "")
            desc  = item.get("description", "") or ""

            if not url or "[Removed]" in title or url == "https://removed.com":
                continue

            h = article_hash(url)
            if h in seen_hashes:
                continue

            log.info(f"  ✓ [General Coverage] {title[:70]}")
            sentiment = analyse_sentiment(title, desc, "General Coverage — Mastercard Foundation Nigeria")

            article = {
                "id":              h,
                "program":         "General Coverage",
                "title":           title,
                "url":             url,
                "source":          item.get("source", {}).get("name", "Unknown"),
                "published":       item.get("publishedAt", datetime.now(timezone.utc).isoformat()),
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

    # ── Save and push ─────────────────────────────────────────────────────────
    results["articles"]       = results["articles"][:500]
    results["total_articles"] = len(results["articles"])
    results["last_updated"]   = datetime.now(timezone.utc).isoformat()

    # Rebuild program summary
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
    log.info(f"NewsAPI calls used this cycle: {api_calls}")
    push_to_github(results)
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

if __name__ == "__main__":
    log.info("IMPACT PULSE — IMC IMPACT / Imaginarium Marketing Communications")
    log.info("Monitoring 15 Mastercard Foundation Nigeria programs via NewsAPI")
    run_crawl()
    scheduler = BlockingScheduler(timezone="Africa/Lagos")
    scheduler.add_job(run_crawl, "interval", minutes=120)
    log.info("Scheduler active — next crawl in 120 minutes")
    scheduler.start()
