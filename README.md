# Reya vs Binance BTC Price Tracker

This repository tracks and compares the **Binance Futures BTCUSDT mark price** against the **Reya BTC market price** (BTCRUSDPERP). The tracking script runs automatically every 5 minutes and maintains a rolling dataset of the last 24 hours (1440 minutes).

## Output Files

Data is updated on every run and stored in the `data/` directory in two formats:
- [btc_reya_vs_binance_1m.csv](data/btc_reya_vs_binance_1m.csv)
- [btc_reya_vs_binance_1m.json](data/btc_reya_vs_binance_1m.json)

Each row contains the exact UTC minute (`ts_utc`), the `binance_mark_close`, `reya_close`, absolute difference (`abs_diff`), percentage difference (`diff_pct`), and the UTC timestamp of the update (`updated_at_utc`). Missing values for an exchange will report as null/empty if an API is temporarily unreachable.

## Local Run Steps

1. Clone the repository to your local machine:
   ```bash
   git clone <your-repo-url>
   cd reya-binance-btc-tracker
   ```
2. Set up a Python virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the tracking script:
   ```bash
   python scripts/compare_prices_5m.py
   ```
   
The data files will be created or overwritten in the `data/` directory.

## Automated 5-Minute Scheduler

A GitHub Actions workflow is set up in `.github/workflows/track-btc-5m.yml`.
This workflow checks out the repository, installs python packages, runs the tracker script, and commits the updated data output automatically using the `GITHUB_TOKEN`.
- **Cron schedule**: The runner executes every 5 minutes (`*/5 * * * *`).
- **Manual Trigger**: You can also launch it manually through the Actions tab via `workflow_dispatch`.

## Configuration (Environment Variables)

You can customize the script behavior using the following environment variables (or by adding them to the GitHub repository's **Settings > Secrets and variables**):

| Variable | Default Value | Description |
|---|---|---|
| `REYA_SYMBOL` | `BTCRUSDPERP` | The target Reya market symbol. |
| `BINANCE_SYMBOL` | `BTCUSDT` | The target Binance futures symbol. |
| `RESOLUTION` | `1m` | Candle resolution (e.g. `1m`). |
| `ROWS` | `1440` | Total number of rolling window rows to keep (default: 24h). |
| `OUT_DIR` | `data` | Directory to save the CSV and JSON formats. |
| `REQUEST_TIMEOUT_SECONDS` | `10` | The network timeout for API calls. |
| `MAX_RETRIES` | `3` | Maximum automatic retries on API 50x errors. |
| `BACKOFF_SECONDS` | `1.0` | Exponential backoff scale factor for retries. |

## Handling Binance 451 Errors

If the Binance API restricts your IP because of legal/regional blocks (HTTP 451), you can configure a valid proxy endpoint.

Change the `BINANCE_BASE_URL` secret/variable (default `https://fapi.binance.com`) to your proxy URL. In GitHub Actions, add a Repository Secret for `BINANCE_BASE_URL`. The script will automatically respect this base URL for Binance queries and proceed normally.

The system is designed with robustness in mind—if the Binance API is completely blocked but Reya is responsive, the tracker will continue to update Reya's prices and write `null` values for Binance until the issue is fixed.
