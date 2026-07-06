# Coinbase Weekly Digest → Telegram

Checks the Coinbase Weekly Market Commentary page daily; if a new article is
out, sends a short digest (key takeaways + BTC/ETH levels) to your Telegram
chat. Runs outside Claude's sandbox since api.telegram.org isn't reachable
from there.

## Files
- `coinbase_weekly_to_telegram.py` — the script
- `requirements.txt` — Python deps
- `.env.example` — copy to `.env` (or set as GitHub Secrets), fill in your values
- `coinbase-digest-workflow.yml` — GitHub Actions schedule (recommended)

## Option A — GitHub Actions (no server needed, recommended)
1. Create a new **private** GitHub repo, push these files into it.
2. Move `coinbase-digest-workflow.yml` into `.github/workflows/coinbase-digest.yml`.
3. In repo Settings → Secrets and variables → Actions, add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `ANTHROPIC_API_KEY` (optional — enables the RU+EN two-block format;
     without it you'll get an EN-only digest)
4. Commit an empty `last_seen.json` containing `{"last_url": null}` so the
   first run has something to compare against.
5. The workflow runs daily at 08:00 UTC, or trigger manually from the
   Actions tab ("Run workflow").

## Option B — Your own Mac (cron)
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`, fill in your token/chat_id, then:
   `export $(cat .env | xargs)`
3. Test once: `python coinbase_weekly_to_telegram.py`
4. Add to crontab (`crontab -e`) to run daily, e.g.:
   `0 9 * * * cd /path/to/folder && export $(cat .env | xargs) && /usr/bin/python3 coinbase_weekly_to_telegram.py >> digest.log 2>&1`
   (Your Mac needs to be on/awake at that time for cron to fire.)

## Notes
- The script scrapes Coinbase's page structure (headings/lists). If Coinbase
  redesigns the page, the parsing may need small tweaks.
- Without `ANTHROPIC_API_KEY`, you get one EN digest, not the RU+EN split.
- `last_seen.json` prevents duplicate sends — don't delete it.
