# Meme_Scrapper

Meme_Scrapper collects memes from a paginated source website and publishes new entries to a Discord channel via webhook.

The project is designed for scheduled automation:
- scrape pages until a known meme ID is found
- publish only newly discovered memes
- persist a checkpoint of the latest 5 seen meme IDs in GitHub Actions variable `KNOWN_MEME_IDS`

## How It Works

1. `main.py` loads environment variables and configures logging.
2. `state.py` reads `KNOWN_MEME_IDS` (JSON array string) from env.
3. `scraper.py` opens the site with Playwright, parses meme blocks, and stops when a known ID appears.
4. `discord_publisher.py` sends scraped memes to Discord with retry/rate-limit handling.
5. `state.py` exports updated checkpoint IDs as GitHub Actions output (`checkpoint_meme_ids`).
6. Workflow updates repo variable `KNOWN_MEME_IDS` with that output.

## Project Structure

- `main.py`: pipeline orchestration (load config, scrape, publish, export checkpoint)
- `scraper.py`: Playwright + BeautifulSoup scraping logic
- `discord_publisher.py`: Discord webhook sending and retry handling
- `state.py`: known-ID parsing and checkpoint output logic
- `models.py`: constants and `Meme` dataclass
- `.github/workflows/daily-meme-scrape.yml`: scheduled GitHub Actions workflow

## Requirements

- Python 3.12 recommended
- Linux/macOS/WSL for local execution
- Internet access for target website and Discord webhook

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps chromium
```

Create `.env` in repository root:

```dotenv
WEBSITE_URL=
DISCORD_WEBHOOK_URL=
KNOWN_MEME_IDS=[]
LOG_LEVEL=
```

Run locally:

```bash
python main.py
```

## Environment Variables

- `WEBSITE_URL` (required): paginated URL including `/str/<page_number>`
- `DISCORD_WEBHOOK_URL` (required): Discord incoming webhook URL
- `KNOWN_MEME_IDS` (required): JSON array string, example `["4395405","4396095"]`
- `LOG_LEVEL` (optional): default `INFO`

Notes:
- `KNOWN_MEME_IDS` must be valid JSON array text.
- Empty array `[]` is valid for first run.
- Invalid or missing `KNOWN_MEME_IDS` causes hard failure.

## GitHub Actions Automation

Workflow file: `.github/workflows/daily-meme-scrape.yml`

Triggers:
- daily schedule: `15 04 * * *` (04:15 UTC)
- manual trigger: `workflow_dispatch`

Workflow behavior:
- validates required config before installing dependencies
- runs scraper/publisher pipeline
- updates repository variable `KNOWN_MEME_IDS` with latest checkpoint IDs

### GitHub Repository Configuration

Go to `Settings -> Secrets and variables -> Actions` and create:

- Secret: `WEBSITE_URL`
- Secret: `DISCORD_WEBHOOK_URL`
- Variable: `KNOWN_MEME_IDS` (set `[]` initially)

Go to `Settings -> Actions -> General -> Workflow permissions`:

- select `Read and write permissions`

This is required because workflow updates Actions variable via GitHub API (`PATCH`).

## Operational Notes

- If there are no new memes, the run exits successfully without publishing.
- Checkpoint uses 5 IDs (`CHECKPOINT_SIZE` in `models.py`).
- Scraper retries page fetches and publisher retries on network/rate-limit errors.
- GitHub cron uses UTC timezone.
