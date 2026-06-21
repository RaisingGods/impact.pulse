"""
IMPACT PULSE Crawler v4 — IMC IMPACT / Imaginarium Marketing Communications
Full-stack Nigerian media monitoring for 15 Mastercard Foundation programs.
Sources: ScraperAPI (Nigerian news) + NewsAPI (fallback) + Twitter/X + YouTube
Strict Claude AI verification for every article.
"""

import os, json, base64, logging, hashlib, requests, time, re
from datetime import datetime, timezone, timedelta
from anthropic import Anthropic
from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("impact_pulse.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ── Environment Variables ─────────────────────────────────────────────────────
ANTHROPIC_KEY      = os.environ.get("ANTHROPIC_KEY", "")
GITHUB_TOKEN       = os.environ.get("GITHUB_TOKEN", "")
NEWS_API_KEY       = os.environ.get("NEWS_API_KEY", "")
SCRAPER_API_KEY    = os.environ.get("SCRAPER_API_KEY", "")
TWITTER_TOKEN      = os.environ.get("TWITTER_BEARER_TOKEN", "")
YOUTUBE_API_KEY    = os.environ.get("YOUTUBE_API_KEY", "")
GITHUB_REPO        = "RaisingGods/impact.pulse"
GITHUB_BRANCH      = "main"
RESULTS_FILE       = "impact_pulse_results.json"

client = Anthropic(api_key=ANTHROPIC_KEY)

# ── Nigerian News Sources (scraped directly via ScraperAPI) ───────────────────
NIGERIAN_NEWS_SOURCES = [
    {"name": "Punch Newspapers",   "rss": "https://punchng.com/feed/",                    "url": "https://punchng.com"},
    {"name": "Premium Times",      "rss": "https://www.premiumtimesng.com/feed/",          "url": "https://premiumtimesng.com"},
    {"name": "The Guardian NG",    "rss": "https://guardian.ng/feed/",                    "url": "https://guardian.ng"},
    {"name": "Vanguard",           "rss": "https://www.vanguardngr.com/feed/",            "url": "https://vanguardngr.com"},
    {"name": "BusinessDay",        "rss": "https://businessday.ng/feed/",                 "url": "https://businessday.ng"},
    {"name": "The Nation",         "rss": "https://thenationonlineng.net/feed/",          "url": "https://thenationonlineng.net"},
    {"name": "Daily Trust",        "rss": "https://dailytrust.com/feed/",                 "url": "https://dailytrust.com"},
    {"name": "Channels TV",        "rss": "https://www.channelstv.com/feed/",             "url": "https://channelstv.com"},
    {"name": "TechCabal",          "rss": "https://techcabal.com/feed/",                  "url": "https://techcabal.com"},
    {"name": "Nairametrics",       "rss": "https://nairametrics.com/feed/",               "url": "https://nairametrics.com"},
    {"name": "The Cable",          "rss": "https://www.thecable.ng/feed",                 "url": "https://thecable.ng"},
    {"name": "Leadership NG",      "rss": "https://leadership.ng/feed/",                  "url": "https://leadership.ng"},
    {"name": "ThisDay Live",       "rss": "https://www.thisdaylive.com/index.php/feed/",  "url": "https://thisdaylive.com"},
    {"name": "Nigerian Tribune",   "rss": "https://tribuneonlineng.com/feed/",            "url": "https://tribuneonlineng.com"},
    {"name": "Sahara Reporters",   "rss": "https://saharareporters.com/rss.xml",          "url": "https://saharareporters.com"},
    {"name": "Pulse NG",           "rss": "https://www.pulse.ng/rss",                    "url": "https://pulse.ng"},
]

# ── 15 Programs — exact names, aliases, states, keywords ─────────────────────
PROGRAMS = {
    "Young Africa Works": {
        "aliases": ["Young Africa Works", "YAW Nigeria", "Youth Employability Booster", "Young Africa YEB"],
        "partners": ["Jobberman"],
        "states": ["Lagos", "Oyo", "Ondo", "Adamawa", "Kano", "Kaduna", "Edo", "Enugu", "Katsina", "Ogun", "Bauchi", "Akwa Ibom", "Benue", "Abuja", "FCT", "Anambra"],
        "themes": ["youth employment", "job placement", "skills training", "employability", "graduate jobs"],
    },
    "Jobberman": {
        "aliases": ["Jobberman", "Jobberman Nigeria", "Jobberman soft skills"],
        "partners": ["Young Africa Works", "Mastercard Foundation"],
        "states": ["Lagos", "Kano", "Abuja"],
        "themes": ["soft skills", "job placement", "employment", "training", "recruitment"],
    },
    "TAFTA": {
        "aliases": ["TAFTA", "Terra Academy for the Arts", "Terra Academy Arts", "TAFTA Nigeria"],
        "partners": ["Mastercard Foundation"],
        "states": ["Ogun", "Lagos"],
        "themes": ["fashion", "arts", "creative", "design", "tailoring", "textiles"],
    },
    "WOFAN ICON 2": {
        "aliases": ["WOFAN", "ICON 2", "Women Farmers Advancement Network", "WOFAN ICON"],
        "partners": ["Mastercard Foundation"],
        "states": ["Kaduna", "Kano", "Nasarawa", "Bauchi", "Gombe", "FCT"],
        "themes": ["women farmers", "female farmers", "agric women", "food production women"],
    },
    "Babban Gona": {
        "aliases": ["Babban Gona", "Babban Gona CAFI", "Babban Gona WEDI"],
        "partners": ["Mastercard Foundation"],
        "states": ["Kano", "Kaduna", "Katsina", "Jigawa", "Nasarawa", "Niger"],
        "themes": ["smallholder farmers", "agric cooperative", "farmer cooperative", "crop yield", "northern farmers"],
    },
    "IITA I-Youth": {
        "aliases": ["IITA", "I-Youth", "IITA I-Youth", "International Institute Tropical Agriculture"],
        "partners": ["Mastercard Foundation"],
        "states": ["Lagos", "Kaduna", "Kano", "Adamawa", "Jigawa"],
        "themes": ["agribusiness youth", "agricultural youth", "youth farming", "agri-entrepreneur"],
    },
    "Scholars Program": {
        "aliases": ["Mastercard Foundation Scholars", "MCF Scholars", "Mastercard Scholars", "Scholars Program"],
        "partners": ["Mastercard Foundation"],
        "states": ["Nationwide"],
        "themes": ["scholarship", "university", "tertiary education", "student funding", "academic award"],
    },
    "Project Juriya": {
        "aliases": ["Project Juriya", "Juriya", "Sa'anwara'Ijumai", "Juriya women"],
        "partners": ["Mastercard Foundation"],
        "states": ["Adamawa", "Kaduna", "Nasarawa"],
        "themes": ["women empowerment north", "northern women", "rural women", "female livelihood"],
    },
    "Ethnocentrique Fashion Future": {
        "aliases": ["Ethnocentrique", "Fashion Future", "Ethnocentrique Fashion"],
        "partners": ["Mastercard Foundation"],
        "states": ["Abia", "Aba"],
        "themes": ["fashion business", "fashion entrepreneur", "Aba fashion", "creative industry"],
    },
    "EDC": {
        "aliases": ["Enterprise Development Centre", "EDC Nigeria", "Pan-Atlantic University EDC", "Transforming Nigerian Youths"],
        "partners": ["Pan-Atlantic University", "Mastercard Foundation"],
        "states": ["Nationwide"],
        "themes": ["SME training", "entrepreneurship", "business development", "vocational", "youth entrepreneur"],
    },
    "FCMB Easylift": {
        "aliases": ["FCMB Easylift", "Easylift", "FCMB women loan", "FCMB rural"],
        "partners": ["FCMB", "Mastercard Foundation"],
        "states": ["Lagos", "Rural Nigeria"],
        "themes": ["microfinance women", "women loan", "financial inclusion", "small business loan", "rural finance"],
    },
    "Songhai Center": {
        "aliases": ["Songhai", "Songhai Center", "Songhai Nigeria", "Songhai agribusiness"],
        "partners": ["Mastercard Foundation"],
        "states": ["Nationwide"],
        "themes": ["agribusiness incubation", "agricultural training", "farm enterprise", "agro-processing"],
    },
    "Christian Aid SEPTP": {
        "aliases": ["Christian Aid SEPTP", "SEPTP", "Christian Aid Nigeria", "Christian Aid economic"],
        "partners": ["Christian Aid", "Mastercard Foundation"],
        "states": ["Nationwide"],
        "themes": ["economic empowerment", "poverty alleviation", "livelihoods", "community development"],
    },
    "WISE Program": {
        "aliases": ["WISE Program", "WISE Nigeria", "IDH WISE", "cassava WISE"],
        "partners": ["IDH", "Mastercard Foundation"],
        "states": ["Lagos", "Badagry"],
        "themes": ["cassava", "women science", "STEM women Nigeria", "agric women Lagos"],
    },
    "TracTrac ISSAM": {
        "aliases": ["TracTrac", "ISSAM", "ISSAM Nigeria", "TracTrac Nigeria"],
        "partners": ["Mastercard Foundation"],
        "states": ["Nasarawa", "Rural Nigeria"],
        "themes": ["monitoring evaluation", "social accountability", "program tracking", "community monitoring"],
    },
}

# ── Nigerian states for geographic detection ──────────────────────────────────
NIGERIAN_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue",
    "Borno", "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu",
    "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi",
    "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo",
    "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe", "Zamfara", "Abuja", "FCT"
]

seen_hashes: set = set()

def article_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def detect_states(text: str) -> list:
    """Detect Nigerian states mentioned in text."""
    text_lower = text.lower()
    return [s for s in NIGERIAN_STATES if s.lower() in text_lower]

def detect_program(text: str) -> str | None:
    """Quick check — does text mention any program alias?"""
    text_lower = text.lower()
    for program, config in PROGRAMS.items():
        all_terms = config["aliases"] + config["partners"] + config["themes"]
        if any(term.lower() in text_lower for term in all_terms[:8]):  # Check first 8 terms
            return program
    # Check for general Mastercard Foundation
    if "mastercard foundation" in text_lower or "mastercard" in text_lower:
        return "General Coverage"
    return None

# ── ScraperAPI RSS fetcher ────────────────────────────────────────────────────
def fetch_rss_via_scraper(rss_url: str, source_name: str) -> list:
    """Fetch RSS feed through ScraperAPI to bypass Nigerian site blocks."""
    if not SCRAPER_API_KEY:
        return fetch_rss_direct(rss_url, source_name)

    try:
        api_url = f"https://api.scraperapi.com/?api_key={SCRAPER_API_KEY}&url={rss_url}&render=false"
        r = requests.get(api_url, timeout=30)
        if r.status_code == 200:
            import feedparser
            feed = feedparser.parse(r.text)
            entries = feed.entries[:20]
            log.info(f"  ScraperAPI [{source_name}]: {len(entries)} entries")
            return entries
        else:
            log.warning(f"  ScraperAPI [{source_name}]: {r.status_code}")
            return []
    except Exception as e:
        log.warning(f"  ScraperAPI error [{source_name}]: {e}")
        return []

def fetch_rss_direct(rss_url: str, source_name: str) -> list:
    """Direct RSS fetch as fallback."""
    try:
        import feedparser
        headers = {"User-Agent": "Mozilla/5.0 (compatible; IMCIMPACTPulse/1.0)"}
        r = requests.get(rss_url, headers=headers, timeout=10)
        feed = feedparser.parse(r.text)
        entries = feed.entries[:20]
        log.info(f"  Direct RSS [{source_name}]: {len(entries)} entries")
        return entries
    except Exception as e:
        log.warning(f"  Direct RSS error [{source_name}]: {e}")
        return []

# ── Twitter/X search ──────────────────────────────────────────────────────────
def fetch_twitter(query: str, max_results: int = 10) -> list:
    """Search Twitter/X for program mentions."""
    if not TWITTER_TOKEN:
        return []
    try:
        headers = {"Authorization": f"Bearer {TWITTER_TOKEN}"}
        params = {
            "query": f"{query} lang:en -is:retweet",
            "max_results": max_results,
            "tweet.fields": "created_at,author_id,text,public_metrics",
            "expansions": "author_id",
            "user.fields": "name,username",
        }
        r = requests.get(
            "https://api.twitter.com/2/tweets/search/recent",
            headers=headers, params=params, timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            tweets = data.get("data", [])
            users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
            results = []
            for t in tweets:
                author = users.get(t.get("author_id", ""), {})
                results.append({
                    "title": t["text"][:150],
                    "url": f"https://twitter.com/{author.get('username','')}/status/{t['id']}",
                    "source": f"@{author.get('username', 'Twitter')}",
                    "published": t.get("created_at", ""),
                    "description": t["text"],
                    "media_type": "social",
                    "platform": "Twitter/X",
                })
            log.info(f"  Twitter [{query[:40]}]: {len(results)} tweets")
            return results
        else:
            log.warning(f"  Twitter error: {r.status_code}")
            return []
    except Exception as e:
        log.warning(f"  Twitter error: {e}")
        return []

# ── YouTube search ────────────────────────────────────────────────────────────
def fetch_youtube(query: str, max_results: int = 5) -> list:
    """Search YouTube for program-related videos."""
    if not YOUTUBE_API_KEY:
        return []
    try:
        params = {
            "part": "snippet",
            "q": f"{query} Nigeria",
            "type": "video",
            "maxResults": max_results,
            "relevanceLanguage": "en",
            "regionCode": "NG",
            "key": YOUTUBE_API_KEY,
        }
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params=params, timeout=15
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            results = []
            for item in items:
                snippet = item.get("snippet", {})
                vid_id = item.get("id", {}).get("videoId", "")
                results.append({
                    "title": snippet.get("title", ""),
                    "url": f"https://youtube.com/watch?v={vid_id}",
                    "source": snippet.get("channelTitle", "YouTube"),
                    "published": snippet.get("publishedAt", ""),
                    "description": snippet.get("description", ""),
                    "media_type": "video",
                    "platform": "YouTube",
                })
            log.info(f"  YouTube [{query[:40]}]: {len(results)} videos")
            return results
        else:
            log.warning(f"  YouTube error: {r.status_code}")
            return []
    except Exception as e:
        log.warning(f"  YouTube error: {e}")
        return []

# ── NewsAPI fallback ──────────────────────────────────────────────────────────
def fetch_newsapi(query: str, days_back: int = 7) -> list:
    if not NEWS_API_KEY:
        return []
    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime('%Y-%m-%d')
    try:
        r = requests.get("https://newsapi.org/v2/everything", params={
            "q": query, "from": from_date, "language": "en",
            "sortBy": "publishedAt", "pageSize": 10, "apiKey": NEWS_API_KEY,
        }, timeout=15)
        if r.status_code == 200:
            items = r.json().get("articles", [])
            results = []
            for item in items:
                if not item.get("url") or "[Removed]" in (item.get("title") or ""):
                    continue
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "source": item.get("source", {}).get("name", "Unknown"),
                    "published": item.get("publishedAt", ""),
                    "description": item.get("description", "") or "",
                    "media_type": "news",
                    "platform": "News",
                })
            log.info(f"  NewsAPI [{query[:40]}]: {len(results)} articles")
            return results
        elif r.status_code == 429:
            time.sleep(60)
            return []
        return []
    except Exception as e:
        log.warning(f"  NewsAPI error: {e}")
        return []

# ── Claude AI verification + analysis ────────────────────────────────────────
def verify_and_analyse(title: str, description: str, program: str, media_type: str = "news") -> dict | None:
    """Strict verification — Claude must confirm relevance before article is added."""

    # Build program context for Claude
    prog_config = PROGRAMS.get(program, {})
    aliases = ", ".join(prog_config.get("aliases", [program]))
    states = ", ".join(prog_config.get("states", []))
    themes = ", ".join(prog_config.get("themes", []))

    prompt = f"""You are a strict Nigerian media analyst for IMC IMPACT monitoring Mastercard Foundation programs.

PROGRAM TO VERIFY: {program}
Known aliases: {aliases}
Operating states: {states}
Key themes: {themes}

CONTENT TO ANALYSE:
Title: {title}
Description: {description[:500]}
Media type: {media_type}

TASK: Determine if this content is GENUINELY about {program} or directly related to Mastercard Foundation Nigeria's work in Nigeria.

Nigerian language note: Content may contain Nigerian Pidgin (e.g. "dem try", "e don work"), Hausa phrases, or Yoruba expressions — treat these as valid Nigerian English variants.

Return ONLY this JSON:
{{
  "is_relevant": true or false,
  "confidence": "high", "medium", or "low",
  "sentiment": "positive", "negative", "neutral", or "mixed",
  "sentiment_score": number -1.0 to 1.0,
  "summary": "max 20 words describing stance if relevant, else empty string",
  "key_theme": "employment", "agriculture", "education", "women empowerment", "entrepreneurship", "policy", "technology", "health", or "other",
  "nigerian_language": "Standard English", "Nigerian Pidgin", "Hausa", "Yoruba", or "Mixed",
  "speaker_type": "participant", "journalist", "government", "influencer", "partner", "researcher", or "unknown",
  "geographic_states": ["list of Nigerian states mentioned or empty array"]
}}

Be STRICT: If content does not directly mention {program} or clearly relate to Mastercard Foundation Nigeria programs, set is_relevant to false."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip().replace("```json","").replace("```","").strip()
        result = json.loads(raw)
        if not result.get("is_relevant", False):
            log.info(f"  ✗ REJECTED: {title[:55]}")
            return None
        if result.get("confidence") == "low":
            log.info(f"  ✗ LOW CONFIDENCE: {title[:55]}")
            return None
        return result
    except Exception as e:
        log.warning(f"  Claude error: {e}")
        return None

# ── GitHub push ───────────────────────────────────────────────────────────────
def push_to_github(results: dict):
    if not GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN not set")
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
    except Exception as e:
        log.warning(f"SHA error: {e}")

    payload = {
        "message": f"Auto-update {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "content": content_b64,
        "branch": GITHUB_BRANCH,
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
                r2 = requests.get(api_url, headers=headers, params={"ref": GITHUB_BRANCH}, timeout=10)
                if r2.status_code == 200:
                    payload["sha"] = r2.json().get("sha")
            else:
                log.error(f"Push failed: {r.status_code} — {r.text[:200]}")
        except Exception as e:
            log.error(f"Push error: {e}")

# ── Process a raw item into IMPACT PULSE article format ───────────────────────
def process_item(item: dict, program: str) -> dict | None:
    title = (item.get("title") or "").strip()
    desc  = (item.get("description") or "").strip()
    url   = (item.get("url") or "").strip()

    if not title or not url:
        return None

    h = article_hash(url)
    if h in seen_hashes:
        return None

    # Quick keyword pre-filter
    text = f"{title} {desc}".lower()
    prog_config = PROGRAMS.get(program, {})
    all_terms = prog_config.get("aliases", []) + [program]
    has_keyword = any(t.lower() in text for t in all_terms)
    has_mastercard = "mastercard" in text or "nigeria" in text

    if not has_keyword and not has_mastercard:
        return None

    # Claude verification
    media_type = item.get("media_type", "news")
    analysis = verify_and_analyse(title, desc, program, media_type)
    if not analysis:
        return None

    # Detect Nigerian states from content
    states_detected = analysis.get("geographic_states", []) or detect_states(f"{title} {desc}")

    article = {
        "id":              h,
        "program":         program,
        "title":           title,
        "url":             url,
        "source":          item.get("source", "Unknown"),
        "platform":        item.get("platform", "News"),
        "published":       item.get("published", datetime.now(timezone.utc).isoformat()),
        "crawled_at":      datetime.now(timezone.utc).isoformat(),
        "sentiment":       analysis.get("sentiment", "neutral"),
        "sentiment_score": analysis.get("sentiment_score", 0.0),
        "summary":         analysis.get("summary", ""),
        "key_theme":       analysis.get("key_theme", "other"),
        "nigerian_language": analysis.get("nigerian_language", "Standard English"),
        "speaker_type":    analysis.get("speaker_type", "unknown"),
        "media_type":      media_type,
        "geographic_states": states_detected,
    }

    seen_hashes.add(h)
    return article

# ── Main crawl ────────────────────────────────────────────────────────────────
def run_crawl():
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info(f"IMPACT PULSE v4 — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    log.info(f"Sources active: ScraperAPI={'YES' if SCRAPER_API_KEY else 'NO'} | Twitter={'YES' if TWITTER_TOKEN else 'NO'} | YouTube={'YES' if YOUTUBE_API_KEY else 'NO'} | NewsAPI={'YES' if NEWS_API_KEY else 'NO'}")

    # Load existing
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
            "geographic_summary": {},
            "platform_summary": {},
        }

    new_count = 0
    rejected  = 0

    # ── LAYER 1: Nigerian News via ScraperAPI ─────────────────────────────────
    log.info("\n── LAYER 1: Nigerian News Sources ──")
    import feedparser
    for source in NIGERIAN_NEWS_SOURCES:
        entries = fetch_rss_via_scraper(source["rss"], source["name"])
        time.sleep(0.5)

        for entry in entries:
            title = getattr(entry, "title", "") or ""
            desc  = getattr(entry, "summary", "") or ""
            url   = getattr(entry, "link", "") or ""
            published = getattr(entry, "published", "") or ""

            # Quick filter — does it mention any program?
            program = detect_program(f"{title} {desc}")
            if not program:
                continue

            item = {
                "title": title, "description": desc, "url": url,
                "source": source["name"], "published": published,
                "media_type": "news", "platform": "News",
            }

            article = process_item(item, program)
            if article:
                results["articles"].insert(0, article)
                new_count += 1
                results["sentiment_overview"][article["sentiment"]] = \
                    results["sentiment_overview"].get(article["sentiment"], 0) + 1
            else:
                rejected += 1

    # ── LAYER 2: Twitter/X Social Listening ───────────────────────────────────
    if TWITTER_TOKEN:
        log.info("\n── LAYER 2: Twitter/X Social Listening ──")
        twitter_queries = [
            ("Young Africa Works", "\"Young Africa Works\" OR \"YAW Nigeria\" Mastercard"),
            ("Jobberman",         "Jobberman Nigeria jobs skills"),
            ("TAFTA",             "TAFTA Nigeria fashion arts"),
            ("Babban Gona",       "\"Babban Gona\" farmers Nigeria"),
            ("WOFAN ICON 2",      "WOFAN Nigeria women farmers"),
            ("Scholars Program",  "\"Mastercard Foundation Scholars\" Nigeria"),
            ("General Coverage",  "\"Mastercard Foundation\" Nigeria programs 2026"),
        ]
        for program, query in twitter_queries:
            tweets = fetch_twitter(query, max_results=10)
            time.sleep(1)
            for tweet in tweets:
                article = process_item(tweet, program)
                if article:
                    results["articles"].insert(0, article)
                    new_count += 1
                    results["sentiment_overview"][article["sentiment"]] = \
                        results["sentiment_overview"].get(article["sentiment"], 0) + 1

    # ── LAYER 3: YouTube ──────────────────────────────────────────────────────
    if YOUTUBE_API_KEY:
        log.info("\n── LAYER 3: YouTube ──")
        yt_queries = [
            ("Young Africa Works", "Young Africa Works Mastercard Foundation Nigeria"),
            ("Jobberman",          "Jobberman Nigeria skills training"),
            ("TAFTA",              "TAFTA Nigeria fashion school"),
            ("Babban Gona",        "Babban Gona farmers Nigeria"),
            ("General Coverage",   "Mastercard Foundation Nigeria youth programs 2026"),
        ]
        for program, query in yt_queries:
            videos = fetch_youtube(query, max_results=5)
            time.sleep(0.5)
            for video in videos:
                article = process_item(video, program)
                if article:
                    results["articles"].insert(0, article)
                    new_count += 1
                    results["sentiment_overview"][article["sentiment"]] = \
                        results["sentiment_overview"].get(article["sentiment"], 0) + 1

    # ── LAYER 4: NewsAPI fallback ─────────────────────────────────────────────
    if NEWS_API_KEY:
        log.info("\n── LAYER 4: NewsAPI Fallback ──")
        fallback_queries = [
            ("Young Africa Works",  "Mastercard Foundation Young Africa Works Nigeria"),
            ("Jobberman",          "Jobberman Nigeria 2026"),
            ("Babban Gona",        "Babban Gona Nigeria"),
            ("Scholars Program",   "Mastercard Foundation Scholars Nigeria"),
            ("General Coverage",   "Mastercard Foundation Nigeria 2026"),
        ]
        for program, query in fallback_queries:
            items = fetch_newsapi(query, days_back=7)
            time.sleep(0.5)
            for item in items:
                article = process_item(item, program)
                if article:
                    results["articles"].insert(0, article)
                    new_count += 1
                    results["sentiment_overview"][article["sentiment"]] = \
                        results["sentiment_overview"].get(article["sentiment"], 0) + 1

    # ── Finalise ──────────────────────────────────────────────────────────────
    results["articles"]       = results["articles"][:500]
    results["total_articles"] = len(results["articles"])
    results["last_updated"]   = datetime.now(timezone.utc).isoformat()

    # Program summary
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

    # Geographic summary
    geo_summary = {}
    for art in results["articles"]:
        for state in art.get("geographic_states", []):
            if state not in geo_summary:
                geo_summary[state] = {"count": 0, "positive": 0, "negative": 0}
            geo_summary[state]["count"] += 1
            if art["sentiment"] in ("positive", "negative"):
                geo_summary[state][art["sentiment"]] += 1
    results["geographic_summary"] = geo_summary

    # Platform summary
    platform_summary = {}
    for art in results["articles"]:
        p = art.get("platform", "News")
        platform_summary[p] = platform_summary.get(p, 0) + 1
    results["platform_summary"] = platform_summary

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    log.info(f"\n{'━'*40}")
    log.info(f"Crawl complete — {new_count} verified articles added")
    log.info(f"Rejected as irrelevant: {rejected}")
    log.info(f"Total in database: {results['total_articles']}")
    log.info(f"Geographic coverage: {len(geo_summary)} Nigerian states")
    push_to_github(results)
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

if __name__ == "__main__":
    log.info("IMPACT PULSE v4 — IMC IMPACT / Imaginarium Marketing Communications")
    log.info("Full-stack Nigerian media monitoring — News + Social + Video")
    run_crawl()
    scheduler = BlockingScheduler(timezone="Africa/Lagos")
    scheduler.add_job(run_crawl, "interval", minutes=120)
    log.info("Scheduler active — next crawl in 120 minutes")
    scheduler.start()
