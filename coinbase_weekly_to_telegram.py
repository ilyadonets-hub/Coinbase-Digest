"""
Coinbase Weekly Market Commentary -> Telegram digest.

Runs OUTSIDE Claude's sandbox (cron / GitHub Actions / your own server),
so it can reach api.telegram.org directly (Claude's sandbox blocks it).

What it does:
1. Checks the Coinbase "Weekly Market Commentary" listing page.
2. If a new article appeared since the last run, scrapes title + key
   takeaways + BTC/ETH key levels.
3. Optionally asks Claude (Anthropic API) to produce a short RU+EN digest
   in the same format we used in chat. If no ANTHROPIC_API_KEY is set,
   falls back to a plain EN-only digest (no translation).
4. Sends the result to your Telegram chat via the Bot API.
5. Remembers the last article URL in last_seen.json so it only fires once
   per new article.

Setup:
    pip install -r requirements.txt
    export TELEGRAM_BOT_TOKEN=...      # from BotFather
    export TELEGRAM_CHAT_ID=...        # your chat id
    export ANTHROPIC_API_KEY=...       # optional, enables RU+EN summary
    python coinbase_weekly_to_telegram.py

Schedule it with cron, launchd, or GitHub Actions (see README.md).
"""

import json
import os
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

LIST_URL = "https://www.coinbase.com/institutional/research-insights/research/weekly-market-commentary"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CoinbaseDigestBot/1.0)"}
STATE_FILE = Path(__file__).with_name("last_seen.json")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_url": None}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_latest_article_url():
    r = requests.get(LIST_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/weekly-market-commentary/weekly-" in href:
            return href if href.startswith("http") else f"https://www.coinbase.com{href}"
    return None


def extract_between(text, start_marker, end_marker):
    start = text.find(start_marker)
    if start == -1:
        return ""
    start += len(start_marker)
    end = text.find(end_marker, start) if end_marker else -1
    return text[start:end if end != -1 else None].strip()


def clean_lines(block, min_len=15):
    lines = [l.strip(" -•").strip() for l in block.split("\n")]
    return [l for l in lines if len(l) >= min_len]


def parse_article(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else url
    text = soup.get_text("\n")

    takeaways_block = extract_between(text, "Key takeaways", "Written by")
    takeaways = clean_lines(takeaways_block)[:6]

    levels = {}
    for asset in ("BTC", "ETH"):
        block = extract_between(text, f"\n{asset}\n", "Scenarios:")
        support = re.search(r"Support:\s*([^\n]+)", block)
        resistance = re.search(r"Resistance:\s*([^\n]+)", block)
        if support or resistance:
            levels[asset] = {
                "support": support.group(1).strip() if support else "",
                "resistance": resistance.group(1).strip() if resistance else "",
            }

    return {"title": title, "url": url, "takeaways": takeaways, "levels": levels}


def build_plain_digest(article):
    lines = [f"*{article['title']}*", ""]
    for t in article["takeaways"]:
        lines.append(f"- {t}")
    if article["levels"]:
        lines.append("")
        for asset, lv in article["levels"].items():
            lines.append(f"{asset}: support {lv['support']} | resistance {lv['resistance']}")
    lines.append("")
    lines.append(article["url"])
    return "\n".join(lines)


def build_ru_en_digest(article):
    """Ask Claude to condense into the RU+EN two-block format we use in chat."""
    if not ANTHROPIC_API_KEY:
        return build_plain_digest(article)

    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    source = build_plain_digest(article)
    prompt = (
        "Сократи этот дайджест Coinbase Weekly до 4-5 буллетов и выведи в двух блоках: "
        "сначала RU, потом EN, каждый начинается с заголовка статьи. "
        "Сохрани числовые уровни BTC/ETH. Формат простой, без лишнего форматирования.\n\n"
        f"{source}"
    )
    msg = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def send_telegram(text):
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        api,
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
        timeout=20,
    )
    resp.raise_for_status()


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env vars", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    latest_url = get_latest_article_url()
    if not latest_url:
        print("Could not find any article on the listing page.")
        return
    if latest_url == state.get("last_url"):
        print("No new article since last check.")
        return

    article = parse_article(latest_url)
    digest = build_ru_en_digest(article)
    send_telegram(digest)

    state["last_url"] = latest_url
    save_state(state)
    print(f"Sent digest for: {article['title']}")


if __name__ == "__main__":
    main()
