import requests
import json
import time
import os
import re
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
import anthropic

GITHUB_TOKEN = os.environ.get('GH_TOKEN', '')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'RaisingGods/impact.pulse')
GITHUB_FILE = 'impact_pulse_results.json'
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# 16 Mastercard Foundation Nigeria programs
# Every search includes "Mastercard Foundation" to ensure relevance
PROGRAMS = [
    {
        "name": "WISE Program",
        "implementer": "IDH",
        "queries": [
            "WISE Program IDH Nigeria Mastercard Foundation",
            "IDH Nigeria sustainable trade Mastercard Foundation",
        ]
    },
    {
        "name": "Jobberman",
        "implementer": "Young Africa Works",
        "queries": [
            "Jobberman Nigeria Mastercard Foundation",
            "Jobberman Young Africa Works Mastercard Foundation",
            "Jobberman youth employment Nigeria Mastercard",
        ]
    },
    {
        "name": "World Food Programme",
        "implementer": "WFP",
        "queries": [
            "World Food Programme Nigeria Mastercard Foundation",
            "WFP Nigeria youth Mastercard Foundation",
        ]
    },
    {
        "name": "Fashion Future Program",
        "implementer": "Ethnocentrique",
        "queries": [
            "Ethnocentrique Fashion Future Nigeria Mastercard Foundation",
            "Fashion Future Program Aba Nigeria Mastercard",
            "Ethnocentrique Nigeria Mastercard Foundation",
        ]
    },
    {
        "name": "Youth Employability Booster",
        "implementer": "Young Africa International",
        "queries": [
            "Young Africa International Nigeria Mastercard Foundation",
            "Youth Employability Booster Nigeria Mastercard Foundation",
        ]
    },
    {
        "name": "Songhai Center",
        "implementer": "Songhai",
        "queries": [
            "Songhai Center Nigeria Mastercard Foundation",
            "Songhai Centre agriculture Nigeria Mastercard Foundation",
        ]
    },
    {
        "name": "Project Juriya",
        "implementer": "SCL / Sa'anwara / Ijumai Consultaire",
        "queries": [
            "Project Juriya Nigeria Mastercard Foundation",
            "Juriya Southern Kaduna Mastercard Foundation",
            "SCL Nigeria Mastercard Foundation Juriya",
            "Ijumai Consultaire Nigeria Mastercard Foundation",
        ]
    },
    {
        "name": "IITA I-Youth",
        "implementer": "IITA",
        "queries": [
            "IITA I-Youth Nigeria Mastercard Foundation",
            "International Institute Tropical Agriculture youth Nigeria Mastercard Foundation",
            "IITA youth employment Nigeria Mastercard",
        ]
    },
    {
        "name": "Babban Gona",
        "implementer": "CAFI & WEDI",
        "queries": [
            "Babban Gona Nigeria Mastercard Foundation",
            "Babban Gona CAFI WEDI Mastercard Foundation",
            "Babban Gona farmers Nigeria Mastercard",
        ]
    },
    {
        "name": "TracTrac ISSAM",
        "implementer": "TracTrac",
        "queries": [
            "TracTrac Nigeria Mastercard Foundation",
            "ISSAM Nigeria agriculture Mastercard Foundation",
            "TracTrac ISSAM Nigeria Mastercard",
        ]
    },
    {
        "name": "TAFTA",
        "implementer": "Terra Academy for the Arts",
        "queries": [
            "TAFTA Nigeria Mastercard Foundation",
            "Terra Academy Arts Nigeria Mastercard Foundation",
            "TAFTA fashion graduates Nigeria Mastercard",
        ]
    },
    {
        "name": "Christian Aid SEPTP",
        "implementer": "Christian Aid",
        "queries": [
            "Christian Aid SEPTP Nigeria Mastercard Foundation",
            "Christian Aid youth employment Nigeria Mastercard Foundation",
            "SEPTP Nigeria Mastercard Foundation",
        ]
    },
    {
        "name": "WOFAN ICON 2",
        "implementer": "Women Farmers Advancement Network",
        "queries": [
            "WOFAN Nigeria Mastercard Foundation",
            "Women Farmers Advancement Network ICON 2 Nigeria Mastercard Foundation",
            "WOFAN ICON 2 Mastercard Foundation",
        ]
    },
    {
        "name": "FCMB Easylift",
        "implementer": "First City Monument Bank",
        "queries": [
            "FCMB Easylift Nigeria Mastercard Foundation",
            "First City Monument Bank Easylift Mastercard Foundation",
            "FCMB youth loan Nigeria Mastercard Foundation",
        ]
    },
    {
        "name": "EDC Transforming Nigerian Youths",
        "implementer": "Enterprise Development Centre",
        "queries": [
            "Enterprise Development Centre Nigeria Mastercard Foundation",
            "EDC Transforming Nigerian Youths Mastercard Foundation",
            "EDC Nigeria youth Mastercard Foundation",
        ]
    },
    {
        "name": "Del-York YAPPI",
        "implementer": "Del-York Group",
        "queries": [
            "Del-York YAPPI Nigeria Mastercard Foundation",
            "Del-York Group Nigeria Mastercard Foundation",
            "YAPPI Nigeria creative arts Mastercard Foundation",
        ]
    },
]

POSITIVE_WORDS = [
    'success', 'launch', 'achieve', 'milestone', 'graduate', 'empower',
    'impact', 'grow', 'expand', 'reach', 'train', 'create', 'job', 'employ',
    'award', 'partner', 'fund', 'invest', 'support', 'opportunity', 'develop',
    'skill', 'place', 'hire', 'transform', 'uplift', 'beneficiar', 'pioneer',
    'breakthrough', 'celebrate', 'complete', 'deliver', 'commission'
]
NEGATIVE_WORDS = [
    'fail', 'scam', 'fraud', 'corrupt', 'abandon', 'delay', 'problem',
    'crisis', 'accuse', 'probe', 'investigate', 'allege', 'concern', 'risk',
    'threat', 'loss', 'protest', 'demand', 'accountability', 'missing'
]


def google_news_rss(query):
    """Fetch Google News RSS — free, no API key needed."""
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-NG&gl=NG&ceid=NG:en"
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; IMCImpactCrawler/2.0)'}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall('.//item')[:5]:
            title = item.findtext('title', '').strip()
            link = item.findtext('link', '').strip()
            pubdate = item.findtext('pubDate', '').strip()
            source = item.findtext('source', '').strip()
            if title and link:
                items.append({
                    'title': title,
                    'url': link,
                    'date': pubdate,
                    'source': source
                })
        return items
    except Exception as e:
        print(f"  RSS error for '{query}': {e}")
        return []


def score_sentiment(title):
    t = title.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in t)
    neg = sum(1 for w in NEGATIVE_WORDS if w in t)
    if neg > 0 and neg >= pos:
        return 'negative'
    if pos > 0:
        return 'positive'
    return 'neutral'


def analyse_with_claude(articles_summary):
    """Use Claude to generate weekly narrative summary."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = f"""You are a senior communications analyst at IMC IMPACT in Nigeria.
Based on these recent media mentions of Mastercard Foundation Nigeria programs, write a concise weekly intelligence summary (max 300 words).

Articles found this week:
{articles_summary}

Write the summary in this format:
WEEKLY INTELLIGENCE SUMMARY
Period: {datetime.now(timezone.utc).strftime('%B %Y')}

AT A GLANCE
[3 bullet points: total mentions, sentiment, top program]

TOP STORY
[Most significant coverage this week]

PRIORITY ALERT
[Any negative or accountability coverage requiring attention. Write NONE if nothing.]

RECOMMENDATIONS
[2-3 specific actions for the communications team]

Keep it factual, professional, and actionable."""

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        print(f"  Claude analysis error: {e}")
        return None


def load_existing():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            import base64
            data = json.loads(base64.b64decode(r.json()['content']).decode())
            sha = r.json()['sha']
            return data, sha
    except Exception as e:
        print(f"  Load error: {e}")
    return None, None


def save_to_github(data, sha=None):
    import base64
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    payload = {
        'message': f'IMPACT PULSE crawl — {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC',
        'content': base64.b64encode(json.dumps(data, indent=2).encode()).decode()
    }
    if sha:
        payload['sha'] = sha
    try:
        r = requests.put(url, headers=headers, json=payload, timeout=20)
        if r.status_code in (200, 201):
            print(f"  GitHub updated successfully")
            return True
        else:
            print(f"  GitHub error: {r.status_code}")
    except Exception as e:
        print(f"  GitHub save error: {e}")
    return False


def crawl():
    print(f"\n{'='*60}")
    print(f"IMPACT PULSE CRAWL — {datetime.now(timezone.utc).isoformat()}")
    print(f"16 Mastercard Foundation Nigeria Programs")
    print(f"{'='*60}")

    existing, sha = load_existing()
    all_articles = existing.get('articles', []) if existing else []
    existing_urls = {a['url'] for a in all_articles}

    new_articles = []
    program_counts = {}

    for prog in PROGRAMS:
        print(f"\n[{prog['name']}]")
        found_for_program = []

        for query in prog['queries']:
            items = google_news_rss(query)
            for item in items:
                if item['url'] in existing_urls:
                    continue
                sentiment = score_sentiment(item['title'])
                article = {
                    'program': prog['name'],
                    'implementer': prog['implementer'],
                    'title': item['title'],
                    'url': item['url'],
                    'source': item['source'],
                    'date': item['date'],
                    'sentiment': sentiment,
                    'crawled_at': datetime.now(timezone.utc).isoformat()
                }
                found_for_program.append(article)
                existing_urls.add(item['url'])
                print(f"  NEW [{sentiment.upper()}]: {item['title'][:70]}")

            time.sleep(1)

        # Deduplicate within program
        seen = set()
        for a in found_for_program:
            if a['url'] not in seen:
                seen.add(a['url'])
                new_articles.append(a)

        program_counts[prog['name']] = len(found_for_program)

    # Merge new articles
    all_articles = all_articles + new_articles

    # Keep last 500 articles
    all_articles = all_articles[-500:]

    # Calculate stats
    total = len(all_articles)
    pos = sum(1 for a in all_articles if a['sentiment'] == 'positive')
    neg = sum(1 for a in all_articles if a['sentiment'] == 'negative')
    neu = sum(1 for a in all_articles if a['sentiment'] == 'neutral')
    pos_rate = round(pos / total * 100) if total else 0

    # Generate AI summary if we have new articles
    ai_summary = existing.get('ai_summary', '') if existing else ''
    if new_articles and ANTHROPIC_API_KEY:
        print(f"\nGenerating AI summary with Claude...")
        articles_text = '\n'.join([
            f"- [{a['program']}] {a['title']} ({a['source']}) [{a['sentiment']}]"
            for a in new_articles[:20]
        ])
        summary = analyse_with_claude(articles_text)
        if summary:
            ai_summary = summary
            print(f"  AI summary generated")

    result = {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'total_articles': total,
        'new_this_run': len(new_articles),
        'sentiment': {'positive': pos, 'negative': neg, 'neutral': neu},
        'positive_rate': pos_rate,
        'ai_summary': ai_summary,
        'program_counts': program_counts,
        'articles': all_articles
    }

    print(f"\n{'='*60}")
    print(f"RESULTS: {len(new_articles)} new articles | {total} total | {pos_rate}% positive")
    print(f"{'='*60}")

    save_to_github(result, sha)
    return result


if __name__ == '__main__':
    print("IMPACT PULSE Crawler v2.0")
    print("Google News RSS | 16 MCF Nigeria Programs")
    crawl()
