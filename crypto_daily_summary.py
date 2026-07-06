"""
Daily plain-language crypto market summary -> Telegram.

Runs OUTSIDE Claude's sandbox (GitHub Actions / cron / your own server) —
same reason as coinbase_weekly_to_telegram.py: api.telegram.org isn't
reachable from Claude's own sandbox.

What it does:
1. Pulls BTC/ETH price + 24h change from CoinGecko (free, no API key).
2. Pulls latest headlines from CoinDesk's RSS feed.
3. If ANTHROPIC_API_KEY is set, asks Claude to write a short, plain-language
   Russian summary — no futures/options/derivatives jargon, just price
   direction and headlines in plain words. Without the key, sends a simple
   bullet list instead.
4. Sends the result to your Telegram chat.

Setup (same env vars as coinbase_weekly_to_telegram.py):
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ANTHROPIC_API_KEY (optional)

Schedule with GitHub Actions (see crypto-daily-summary-workflow.yml) or cron.
"""

import os
import sys
import xml.etree.ElementTree as ET

import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"
)
COINDESK_RSS = "https://www.coindesk.com/arc/outboundfeeds/rss/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CryptoDailySummaryBot/1.0)"}


def get_prices():
    r = requests.get(COINGECKO_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    return {
        "BTC": {"usd": data["bitcoin"]["usd"], "change": data["bitcoin"]["usd_24h_change"]},
        "ETH": {"usd": data["ethereum"]["usd"], "change": data["ethereum"]["usd_24h_change"]},
    }


def get_headlines(limit=8):
    r = requests.get(COINDESK_RSS, headers=HEADERS, timeout=20)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    headlines = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        if title:
            headlines.append(title)
    return headlines


def build_plain_summary(prices, headlines):
    lines = ["Крипторынок сегодня:", ""]
    for asset, d in prices.items():
        sign = "+" if d["change"] >= 0 else ""
        lines.append(f"{asset}: ${d['usd']:,.0f} ({sign}{d['change']:.1f}% за 24ч)")
    lines.append("")
    lines.append("Главные новости:")
    for h in headlines[:6]:
        lines.append(f"- {h}")
    return "\n".join(lines)


def build_llm_summary(prices, headlines):
    """Ask Claude for a short, jargon-free RU summary. Falls back to a plain
    bullet list if no ANTHROPIC_API_KEY is configured."""
    raw = build_plain_summary(prices, headlines)
    if not ANTHROPIC_API_KEY:
        return raw

    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = (
        "Напиши короткое (5-7 предложений) саммари по крипторынку на русском, "
        "простым языком. Без сложных терминов, без упоминания фьючерсов, "
        "опционов, деривативов, волатильности и т.п. Только цены, общее "
        "направление рынка и главные новости своими словами, понятно "
        "неспециалисту.\n\nСырые данные:\n\n" + raw
    )
    msg = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def send_telegram(text):
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        api, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=20
    )
    resp.raise_for_status()


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env vars", file=sys.stderr)
        sys.exit(1)

    prices = get_prices()
    headlines = get_headlines()
    summary = build_llm_summary(prices, headlines)
    send_telegram(summary)
    print("Sent daily crypto summary.")


if __name__ == "__main__":
    main()
