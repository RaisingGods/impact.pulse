"""
╔══════════════════════════════════════════════════════════════════╗
║           IMPACT PULSE — Media Intelligence Crawler             ║
║           Imaginarium Marketing Communications (IMC IMPACT)     ║
║           Version 1.0 · Built for Mastercard Foundation         ║
╚══════════════════════════════════════════════════════════════════╝

HOW TO RUN:
  1. Paste your Anthropic API key below where it says PASTE-YOUR-KEY-HERE
  2. Open your terminal / Command Prompt
  3. Navigate to this folder: cd impact-pulse-crawler
  4. Run: python impact_pulse_crawler.py

The crawler will:
  → Check 12 Nigerian news sources every 2 hours
  → Detect mentions of all 15 Mastercard Foundation programs
  → Analyse sentiment in English, Pidgin, Hausa, and Yoruba
  → Save results to impact_pulse_results.json
  → Print alerts to your terminal for anything critical

REQUIREMENTS (install once):
  pip install feedparser requests beautifulsoup4 anthropic apscheduler
"""

import feedparser
import requests
import json
import os
import re
import time
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from anthropic import Anthropic
from apscheduler.schedulers.blocking import BlockingScheduler

# ─────────────────────────────────────────────
#  ★  PASTE YOUR ANTHROPIC API KEY HERE  ★
# ─────────────────────────────────────────────
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
# ─────────────────────────────────────────────

# ── CONFIGURATION ──────────────────────────────────────────────
RESULTS_FILE   = "impact_pulse_results.json"
LOG_FILE       = "impact_pulse.log"
CRAWL_INTERVAL = 120   # minutes between crawls (2 hours)
MAX_RESULTS    = 500   # keep last N results in the JSON file

# ── LOGGING SETUP ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("impact_pulse")

# ── 15 MASTERCARD FOUNDATION NIGERIA PROGRAMS ──────────────────
PROGRAMS = {
    "Young Africa Works": [
        "Young Africa Works", "YAW", "Africa Works",
        "Jobberman Young Africa", "youth employment mastercard"
    ],
    "Jobberman": [
        "Jobberman", "Jobberman Nigeria", "Jobberman YAW",
        "Jobberman mastercard", "jobberman foundation"
    ],
    "TAFTA": [
        "TAFTA", "Technical and Fashion Training", "fashion future program",
        "Fashion Future Programme", "Ethnocentrique", "TAFTA Nigeria"
    ],
    "WOFAN ICON 2": [
        "WOFAN ICON", "WOFAN", "Women Farmers Advancement Network",
        "ICON 2 Nigeria", "WOFAN mastercard"
    ],
    "Babban Gona": [
        "Babban Gona", "CAFI", "Babban Gona CAFI", "Babban Gona Nigeria",
        "WEDI Babban Gona", "Babban Gona mastercard"
    ],
    "IITA I-Youth": [
        "IITA I-Youth", "IITA Youth Agripreneurs", "IITA Nigeria",
        "IITA mastercard", "I-Youth Nigeria"
    ],
    "Scholars Program": [
        "Mastercard Foundation Scholars", "MCF Scholars",
        "PAU Mastercard", "Pan-Atlantic University mastercard",
        "mastercard foundation scholarship Nigeria"
    ],
    "Project Juriya": [
        "Project Juriya", "Juriya", "SCL Nigeria mastercard",
        "Southern Kaduna mastercard", "Juriya farmers"
    ],
    "Ethnocentrique Fashion Future": [
        "Ethnocentrique", "Fashion Future Aba", "Aba fashion mastercard",
        "fashion future programme Aba"
    ],
    "EDC Youth Entrepreneurship": [
        "EDC Nigeria", "Enterprise Development Centre mastercard",
        "EDC youth mastercard", "Pan-Atlantic EDC"
    ],
    "FCMB Easylift": [
        "FCMB Easylift", "Easylift FCMB", "FCMB mastercard foundation",
        "Easylift mastercard"
    ],
    "Songhai Center": [
        "Songhai Center Nigeria", "Songhai mastercard",
        "AIRBDA Songhai", "Songhai agricultural mastercard"
    ],
    "Christian Aid SEPTP": [
        "Christian Aid Nigeria mastercard", "SEPTP mastercard",
        "Christian Aid SEPTP", "sustainable livelihoods mastercard Nigeria"
    ],
    "WISE Program": [
        "WISE Program mastercard", "IDH mastercard Nigeria",
        "cassava mastercard Nigeria", "Badagry mastercard"
    ],
    "TracTrac / ISSAM": [
        "TracTrac Nigeria", "ISSAM mastercard", "agricultural tracking mastercard Nigeria"
    ],
}

# ── ALL KEYWORDS (flat list for quick scanning) ─────────────────
ALL_KEYWORDS = (
    list(PROGRAMS.keys()) +
    [kw for kws in PROGRAMS.values() for kw in kws] +
    [
        "Mastercard Foundation Nigeria",
        "Mastercard Foundation",
        "mastercard foundation nigeria",
        "MCF Nigeria",
    ]
)
# Deduplicate, lowercase for matching
SEARCH_TERMS = list({k.lower() for k in ALL_KEYWORDS})

# ── NIGERIAN NEWS SOURCES (RSS FEEDS) ──────────────────────────
SOURCES = [
    # Tier 1 National
    {"name": "Punch Newspapers",   "url": "https://punchng.com/feed/",              "tier": 1},
    {"name": "Premium Times",      "url": "https://www.premiumtimesng.com/feed/",    "tier": 1},
    {"name": "The Guardian NG",    "url": "https://guardian.ng/feed/",               "tier": 1},
    {"name": "Vanguard",           "url": "https://www.vanguardngr.com/feed/",       "tier": 1},
    {"name": "BusinessDay",        "url": "https://businessday.ng/feed/",            "tier": 1},
    {"name": "ThisDay Live",       "url": "https://www.thisdaylive.com/index.php/feed/", "tier": 1},
    # Tier 2 National
    {"name": "Daily Trust",        "url": "https://dailytrust.com/feed",             "tier": 2},
    {"name": "The Cable",          "url": "https://www.thecable.ng/feed",            "tier": 2},
    {"name": "Leadership NG",      "url": "https://leadership.ng/feed/",             "tier": 2},
    {"name": "Sahara Reporters",   "url": "https://saharareporters.com/rss.xml",     "tier": 2},
    # Digital / Youth
    {"name": "Bella Naija",        "url": "https://www.bellanaija.com/feed/",        "tier": 2},
    {"name": "Nigeria Startup News","url": "https://nigeriaSN.com/feed/",            "tier": 2},
]


# ════════════════════════════════════════════════════════════════
#  CORE FUNCTIONS
# ════════════════════════════════════════════════════════════════

def load_results():
    """Load existing results from JSON file."""
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_results(results):
    """Save results to JSON file, keeping only the last MAX_RESULTS."""
    results = results[-MAX_RESULTS:]
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def already_seen(url, results):
    """Check if we have already processed this article URL."""
    seen_urls = {r.get("url") for r in results}
    return url in seen_urls


def detect_programs(text):
    """Return list of matched Mastercard Foundation programs in text."""
    text_lower = text.lower()
    matched = []
    for program, keywords in PROGRAMS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                matched.append(program)
                break
    return list(set(matched))


def is_relevant(title, summary):
    """Quick pre-filter: is this article likely about MCF programs?"""
    combined = (title + " " + summary).lower()
    # Must contain at least one search term
    return any(term in combined for term in SEARCH_TERMS)


def fetch_article_text(url):
    """Fetch full article text from URL."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; IMPACTWatch/1.0)"}
        resp = requests.get(url, timeout=12, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove nav, ads, footer
        for tag in soup(["nav", "footer", "aside", "script", "style", "ads"]):
            tag.decompose()
        # Try article tag first, then body
        article = soup.find("article") or soup.find("main") or soup.body
        if article:
            return " ".join(article.get_text(separator=" ").split())[:3000]
    except Exception as e:
        log.warning(f"Could not fetch article text: {e}")
    return ""


def analyse_with_claude(title, text, source_name, programs_found):
    """Send article to Claude for Nigerian-specific sentiment analysis."""
    client = Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""You are a Nigerian media intelligence analyst for Imaginarium Marketing Communications (IMC IMPACT).

Analyse this news article about Mastercard Foundation Nigeria programs.

SOURCE: {source_name}
HEADLINE: {title}
PROGRAMS DETECTED: {', '.join(programs_found) if programs_found else 'General MCF mention'}
ARTICLE TEXT:
{text[:2000]}

Return a JSON object with exactly these fields:
{{
  "sentiment": "positive" | "negative" | "neutral" | "critical" | "skeptical" | "advocacy",
  "sentiment_score": <number 0-100, where 100 is most positive>,
  "tone_summary": "<one sentence describing the article tone>",
  "key_narrative": "<the main narrative or story being told in 15 words or less>",
  "pidgin_signals": "<any Nigerian Pidgin expressions or signals detected, or 'none'>",
  "hausa_signals": "<any Hausa language signals detected, or 'none'>",
  "yoruba_signals": "<any Yoruba language signals detected, or 'none'>",
  "alert_level": "none" | "watch" | "critical",
  "alert_reason": "<why this needs attention, or 'none'>",
  "programs_confirmed": [<list of confirmed program names from the article>],
  "impact_stats": "<any impact numbers mentioned e.g. '10,000 jobs, 4,000 MSMEs', or 'none'>",
  "journalist": "<journalist or author name if mentioned, or 'unknown'>",
  "is_tier1": <true if this is a major national outlet article, false otherwise>,
  "recommended_action": "<one specific action for the communications team, or 'monitor'>"
}}

Return ONLY the JSON object. No preamble, no explanation."""

    try:
        response = client.messages.create(
          model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        # Strip any markdown code fences if present
        raw = re.sub(r"```json|```", "", raw).strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning(f"Claude returned invalid JSON: {e}")
        return {
            "sentiment": "neutral",
            "sentiment_score": 50,
            "tone_summary": "Analysis unavailable",
            "key_narrative": title[:80],
            "pidgin_signals": "none",
            "hausa_signals": "none",
            "yoruba_signals": "none",
            "alert_level": "none",
            "alert_reason": "none",
            "programs_confirmed": programs_found,
            "impact_stats": "none",
            "journalist": "unknown",
            "is_tier1": False,
            "recommended_action": "monitor"
        }
    except Exception as e:
        log.error(f"Claude API error: {e}")
        raise


def print_alert(result):
    """Print a formatted alert to the terminal for critical findings."""
    level = result.get("alert_level", "none")
    if level == "none":
        return
    border = "🔴" if level == "critical" else "🟡"
    print(f"\n{border * 40}")
    print(f"  {border}  ALERT [{level.upper()}] — {result['source']}")
    print(f"  HEADLINE: {result['title']}")
    print(f"  PROGRAMS: {', '.join(result.get('programs_confirmed', []))}")
    print(f"  SENTIMENT: {result['analysis']['sentiment']} ({result['analysis']['sentiment_score']}/100)")
    print(f"  NARRATIVE: {result['analysis']['key_narrative']}")
    print(f"  REASON: {result['analysis']['alert_reason']}")
    print(f"  ACTION: {result['analysis']['recommended_action']}")
    print(f"  URL: {result['url']}")
    print(f"{border * 40}\n")


# ════════════════════════════════════════════════════════════════
#  MAIN CRAWL FUNCTION
# ════════════════════════════════════════════════════════════════

def run_crawl():
    """Main crawl cycle — runs every CRAWL_INTERVAL minutes."""
    log.info("=" * 60)
    log.info("IMPACT PULSE — Starting crawl cycle")
    log.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    results = load_results()
    new_count = 0
    alert_count = 0

    for source in SOURCES:
        log.info(f"Checking {source['name']} ...")
        try:
            feed = feedparser.parse(source["url"])
            articles = feed.entries[:20]  # Check last 20 articles per source
        except Exception as e:
            log.warning(f"  ✗ Could not fetch {source['name']}: {e}")
            continue

        for entry in articles:
            title   = entry.get("title", "").strip()
            url     = entry.get("link", "").strip()
            summary = entry.get("summary", "").strip()
            pub_date = entry.get("published", datetime.now().isoformat())

            # Skip if already processed
            if already_seen(url, results):
                continue

            # Quick relevance check before spending API credits
            if not is_relevant(title, summary):
                continue

            # Fetch full article text
            log.info(f"  ✓ Relevant: {title[:70]}...")
            full_text = fetch_article_text(url)

            # Detect which programs are mentioned
            programs_found = detect_programs(title + " " + summary + " " + full_text)
            if not programs_found:
                programs_found = ["Mastercard Foundation — general mention"]

            # Send to Claude for analysis
            try:
                log.info(f"    → Sending to Claude for analysis...")
                analysis = analyse_with_claude(title, full_text or summary, source["name"], programs_found)
            except Exception as e:
                log.error(f"    ✗ Analysis failed: {e}")
                time.sleep(5)  # Brief pause before retrying next article
                continue

            # Build result record
            result = {
                "id": f"{source['name'].replace(' ', '_')}_{int(time.time())}",
                "title": title,
                "url": url,
                "source": source["name"],
                "source_tier": source["tier"],
                "published": pub_date,
                "crawled_at": datetime.now().isoformat(),
                "programs_detected": programs_found,
                "programs_confirmed": analysis.get("programs_confirmed", programs_found),
                "sentiment": analysis.get("sentiment", "neutral"),
                "sentiment_score": analysis.get("sentiment_score", 50),
                "alert_level": analysis.get("alert_level", "none"),
                "analysis": analysis,
            }

            results.append(result)
            new_count += 1

            # Alert if needed
            if analysis.get("alert_level") in ("critical", "watch"):
                print_alert(result)
                alert_count += 1

            # Small pause to respect rate limits
            time.sleep(2)

        # Pause between sources
        time.sleep(3)

    # Save all results
    save_results(results)

    # Summary
    log.info("")
    log.info(f"Crawl complete — {new_count} new articles processed")
    log.info(f"Alerts generated: {alert_count}")
    log.info(f"Total records in database: {len(results)}")
    log.info(f"Results saved to: {RESULTS_FILE}")
    log.info("")


# ════════════════════════════════════════════════════════════════
#  SCHEDULER — Run every 2 hours, 24/7
# ════════════════════════════════════════════════════════════════

def main():
    # Validate API key
    if ANTHROPIC_KEY == "PASTE-YOUR-KEY-HERE" or not ANTHROPIC_KEY.startswith("sk-"):
        print("\n" + "=" * 60)
        print("  ERROR: Please paste your Anthropic API key")
        print("  Open this file and replace PASTE-YOUR-KEY-HERE")
        print("  with your actual key from console.anthropic.com")
        print("=" * 60 + "\n")
        return

    print("\n" + "=" * 60)
    print("  IMPACT PULSE — Media Intelligence Crawler")
    print("  Imaginarium Marketing Communications (IMC IMPACT)")
    print("  Monitoring 15 Mastercard Foundation programs")
    print(f"  Crawling every {CRAWL_INTERVAL} minutes | 12 sources")
    print("=" * 60)
    print(f"\n  Results file: {RESULTS_FILE}")
    print(f"  Log file:     {LOG_FILE}")
    print("\n  Press Ctrl+C at any time to stop.\n")

    # Run once immediately on startup
    run_crawl()

    # Then schedule to run every CRAWL_INTERVAL minutes
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_crawl,
        "interval",
        minutes=CRAWL_INTERVAL,
        id="impact_pulse_crawl"
    )

    print(f"\n  Next crawl in {CRAWL_INTERVAL} minutes. Crawler is running...\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\n  Crawler stopped. Results saved to", RESULTS_FILE)


if __name__ == "__main__":
    main()
