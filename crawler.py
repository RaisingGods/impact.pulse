import requests
import json
import time
import os
import re
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

GITHUB_TOKEN = os.environ.get('GH_TOKEN', '')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'RaisingGods/impact.pulse')
GITHUB_FILE = 'pulse_live.json'

# Google Custom Search API credentials
GOOGLE_CSE_KEY = os.environ.get('GOOGLE_CSE_KEY', '')
GOOGLE_CSE_ID  = os.environ.get('GOOGLE_CSE_ID', '')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

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
        ]
    },
    {
        "name": "World Food Programme",
        "implementer": "WFP",
        "queries": [
            "World Food Programme Nigeria Mastercard Foundation",
            "WFP Nigeria Mastercard Foundation",
        ]
    },
    {
        "name": "Fashion Future Program",
        "implementer": "Ethnocentrique",
        "queries": [
            "Ethnocentrique Fashion Future Nigeria Mastercard Foundation",
            "Fashion Future Program Aba Nigeria Mastercard",
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
            "SCL Nigeria Mastercard Foundation Juriya",
        ]
    },
    {
        "name": "IITA I-Youth",
        "implementer": "IITA",
        "queries": [
            "IITA I-Youth Nigeria Mastercard Foundation",
            "IITA youth Nigeria Mastercard Foundation",
        ]
    },
    {
        "name": "Babban Gona",
        "implementer": "CAFI & WEDI",
        "queries": [
            "Babban Gona Nigeria Mastercard Foundation",
            "Babban Gona farmers Nigeria Mastercard",
        ]
    },
    {
        "name": "TracTrac ISSAM",
        "implementer": "TracTrac",
        "queries": [
            "TracTrac Nigeria Mastercard Foundation",
            "ISSAM Nigeria agriculture Mastercard Foundation",
        ]
    },
    {
        "name": "TAFTA",
        "implementer": "Terra Academy for the Arts",
        "queries": [
            "TAFTA Nigeria Mastercard Foundation",
            "Terra Academy Arts Nigeria Mastercard Foundation",
        ]
    },
    {
        "name": "Christian Aid SEPTP",
        "implementer": "Christian Aid",
        "queries": [
            "Christian Aid SEPTP Nigeria Mastercard Foundation",
            "SEPTP Nigeria Mastercard Foundation",
        ]
    },
    {
        "name": "WOFAN ICON 2",
        "implementer": "Women Farmers Advancement Network",
        "queries": [
            "WOFAN Nigeria Mastercard Foundation",
            "WOFAN ICON 2 Mastercard Foundation",
        ]
    },
    {
        "name": "FCMB Easylift",
        "implementer": "First City Monument Bank",
        "queries": [
            "FCMB Easylift Nigeria Mastercard Foundation",
            "FCMB youth Nigeria Mastercard Foundation",
        ]
    },
    {
        "name": "EDC Transforming Nigerian Youths",
        "implementer": "Enterprise Development Centre",
        "queries": [
            "Enterprise Development Centre Nigeria Mastercard Foundation",
            "EDC Transforming Nigerian Youths Mastercard Foundation",
        ]
    },
    {
        "name": "Del-York YAPPI",
        "implementer": "Del-York Group",
        "queries": [
            "Del-York YAPPI Nigeria Mastercard Foundation",
            "YAPPI Nigeria Mastercard Foundation",
        ]
    },
]

POSITIVE_WORDS = [
    'success','launch','achieve','milestone','graduate','empower','impact',
    'grow','expand','reach','train','create','job','employ','award','partner',
    'fund','invest','support','opportunity','develop','skill','place','hire',
    'transform','uplift','beneficiar','pioneer','celebrate','complete','deliver'
]
NEGATIVE_WORDS = [
    'fail','scam','fraud','corrupt','abandon','delay','problem','crisis',
    'accuse','probe','investigate','allege','concern','risk','threat','loss',
    'protest','demand','accountability','missing','graveyard','ghost',
    'collapse','betray','dormant','overgrown','unused','abandoned','wasted',
    'communities demand','press statement','audit','non-performance',
    'rusting','unfulfilled','promises broken','failed project'
]


def google_news_rss(query):
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
        print(f"  RSS error: {e}")
        return []


def google_custom_search(query):
    """Search using Google Custom Search API — finds body-text mentions RSS misses."""
    if not GOOGLE_CSE_KEY or not GOOGLE_CSE_ID:
        return []
    try:
        url = 'https://www.googleapis.com/customsearch/v1'
        params = {
            'key': GOOGLE_CSE_KEY,
            'cx': GOOGLE_CSE_ID,
            'q': query,
            'num': 10,
            'lr': 'lang_en',
            'gl': 'ng',
            'dateRestrict': 'm1',  # last 1 month only
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        items = data.get('items', [])
        results = []
        for item in items:
            title = item.get('title', '')
            link  = item.get('link', '')
            snippet = item.get('snippet', '')
            source = item.get('displayLink', '')
            # Only include if Mastercard Foundation mentioned in title or snippet
            combined = (title + ' ' + snippet).lower()
            if 'mastercard' not in combined and 'mastercard foundation' not in combined:
                continue
            results.append({
                'title':  title,
                'url':    link,
                'source': source,
                'date':   '',
                'snippet': snippet,
            })
        if results:
            print(f"    CSE found {len(results)} result(s) for: {query[:50]}")
        return results
    except Exception as e:
        print(f"    CSE error: {e}")
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


def analyse_with_claude(articles_text):
    """Generate AI weekly summary using Anthropic API."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        headers = {
            'x-api-key': ANTHROPIC_API_KEY,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        }
        prompt = f"""You are a senior communications analyst at IMC IMPACT Nigeria.
Based on these recent media mentions of Mastercard Foundation Nigeria programs, write a concise weekly intelligence summary.

Articles found:
{articles_text}

Write in this format:
WEEKLY INTELLIGENCE SUMMARY
Period: {datetime.now(timezone.utc).strftime('%B %Y')}

AT A GLANCE
- Total mentions this run: [number]
- Overall sentiment: [positive/mixed]
- Top performing program: [name]

TOP STORY
[Most significant coverage in 2 sentences]

PRIORITY ALERT
[Any negative coverage requiring attention. Write NONE if nothing critical.]

RECOMMENDATIONS
1. [Action]
2. [Action]
3. [Action]

Keep it factual, professional, and under 250 words."""

        payload = {
            'model': 'claude-sonnet-4-6',
            'max_tokens': 600,
            'messages': [{'role': 'user', 'content': prompt}]
        }
        r = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers=headers,
            json=payload,
            timeout=30
        )
        if r.status_code == 200:
            return r.json()['content'][0]['text']
        else:
            print(f"  Claude API error: {r.status_code} {r.text[:100]}")
            return None
    except Exception as e:
        print(f"  Claude error: {e}")
        return None


def load_existing():
    """Load current JSON from GitHub."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            import base64
            content = r.json()
            data = json.loads(base64.b64decode(content['content']).decode())
            sha = content['sha']
            return data, sha
        elif r.status_code == 404:
            print("  No existing file — will create new")
            return None, None
    except Exception as e:
        print(f"  Load error: {e}")
    return None, None


def save_to_github(data, sha=None):
    """Save results JSON to GitHub with retry on 409 conflict."""
    import base64

    # Always get fresh SHA before saving to avoid 409 conflicts
    fresh_sha = sha
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }

    # Get latest SHA
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            fresh_sha = r.json()['sha']
    except:
        pass

    payload = {
        'message': f'IMPACT PULSE — {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC — {data.get("total_articles", 0)} articles',
        'content': base64.b64encode(json.dumps(data, indent=2, ensure_ascii=False).encode()).decode()
    }
    if fresh_sha:
        payload['sha'] = fresh_sha

    try:
        r = requests.put(url, headers=headers, json=payload, timeout=20)
        if r.status_code in (200, 201):
            print(f"  GitHub updated — {data.get('total_articles', 0)} total articles saved")
            return True
        else:
            print(f"  GitHub save error: {r.status_code} — {r.text[:150]}")
    except Exception as e:
        print(f"  GitHub exception: {e}")
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
        seen_urls = set()

        for query in prog['queries']:
            # RSS crawl — headline matches
            items = google_news_rss(query)
            for item in items:
                if item['url'] in existing_urls:
                    continue
                if item['url'] in seen_urls:
                    continue
                seen_urls.add(item['url'])
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
                print(f"  NEW RSS [{sentiment.upper()}]: {item['title'][:70]}")

            # CSE crawl — body text matches (catches articles RSS misses)
            cse_items = google_custom_search(query)
            for item in cse_items:
                if item['url'] in existing_urls:
                    continue
                if item['url'] in seen_urls:
                    continue
                seen_urls.add(item['url'])
                sentiment = score_sentiment(item['title'] + ' ' + item.get('snippet',''))
                article = {
                    'program': prog['name'],
                    'implementer': prog['implementer'],
                    'title': item['title'],
                    'url': item['url'],
                    'source': item['source'],
                    'date': item['date'],
                    'sentiment': sentiment,
                    'found_by': 'cse',
                    'crawled_at': datetime.now(timezone.utc).isoformat()
                }
                found_for_program.append(article)
                existing_urls.add(item['url'])
                print(f"  NEW CSE [{sentiment.upper()}]: {item['title'][:70]}")
            time.sleep(1)

        new_articles.extend(found_for_program)
        program_counts[prog['name']] = len(found_for_program)

    # General Mastercard Foundation CSE search — catches body-text mentions
    # that program-specific queries miss (e.g. opinion pieces, Saturday Magazine)
    print("\n[General MCF Search — CSE body text]")
    general_queries = [
        '"Mastercard Foundation" Nigeria',
        '"Mastercard Foundation" Nigeria youth',
        '"Mastercard Foundation" Nigeria programme',
    ]
    seen_general = {a['url'] for a in all_articles + new_articles}
    for gq in general_queries:
        cse_results = google_custom_search(gq)
        for item in cse_results:
            if item['url'] in seen_general:
                continue
            seen_general.add(item['url'])
            sentiment = score_sentiment(item['title'] + ' ' + item.get('snippet', ''))
            article = {
                'program': 'General / Mastercard Foundation',
                'implementer': 'Mastercard Foundation',
                'title': item['title'],
                'url': item['url'],
                'source': item['source'],
                'date': item['date'],
                'sentiment': sentiment,
                'found_by': 'cse_general',
                'crawled_at': datetime.now(timezone.utc).isoformat()
            }
            new_articles.append(article)
            print(f"  NEW GENERAL CSE [{sentiment.upper()}]: {item['title'][:70]}")

    # Merge and keep last 500
    # Only update if we found articles OR existing is empty
    if new_articles or not all_articles:
        all_articles = all_articles + new_articles
        all_articles = all_articles[-500:]
    else:
        print(f"  No new articles found — preserving {len(all_articles)} existing")

    # Stats
    total = len(all_articles)
    pos = sum(1 for a in all_articles if a['sentiment'] == 'positive')
    neg = sum(1 for a in all_articles if a['sentiment'] == 'negative')
    neu = sum(1 for a in all_articles if a['sentiment'] == 'neutral')
    pos_rate = round(pos / total * 100) if total else 0

    # AI summary
    ai_summary = existing.get('ai_summary', '') if existing else ''
    if new_articles and ANTHROPIC_API_KEY:
        print(f"\nGenerating AI summary...")
        articles_text = '\n'.join([
            f"- [{a['program']}] {a['title']} [{a['sentiment']}]"
            for a in new_articles[:20]
        ])
        summary = analyse_with_claude(articles_text)
        if summary:
            ai_summary = summary
            print(f"  AI summary generated successfully")

    # Hardcoded priority alerts — real verified events
    priority_alerts = [
        {
            'id': 'juriya_ccsk_2026',
            'level': 'CRISIS',
            'program': 'Project Juriya',
            'title': 'CCSK Press Statement: Southern Kaduna Communities Demand Accountability as Juriya Agricultural Project Collapses',
            'summary': 'Concerned Citizens of Southern Kaduna issued formal press statement 19 June 2026. Demo farms abandoned across 12+ communities. Formal demands for independent audit within 90 days, suspension of SCL disbursements. Ruben Abati has amplified nationally.',
            'date': '2026-06-19',
            'source': 'CCSK / The Nation / Ruben Abati Blog',
            'communities': 'Kurmin Gwazah, Kudah, Ikkah Gida, Kurmin Sara, Assako, Anchuna, Kamuru, Ungwan Akau, Kubacha',
            'demands': ['Independent 90-day audit', 'Suspend SCL disbursements', 'SCL public report', 'Hand over farms to cooperatives'],
            'status': 'ACTIVE'
        }
    ]

    result = {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'total_articles': total,
        'new_this_run': len(new_articles),
        'sentiment': {'positive': pos, 'negative': neg, 'neutral': neu},
        'positive_rate': pos_rate,
        'ai_summary': ai_summary,
        'program_counts': program_counts,
        'priority_alerts': priority_alerts,
        'articles': all_articles
    }

    print(f"\n{'='*60}")
    print(f"RESULTS: {len(new_articles)} new | {total} total | {pos_rate}% positive")
    print(f"{'='*60}")

    save_to_github(result, sha)
    return result


if __name__ == '__main__':
    print("IMPACT PULSE Crawler v2.1")
    print("Google News RSS | 16 MCF Nigeria Programs")
    crawl()
