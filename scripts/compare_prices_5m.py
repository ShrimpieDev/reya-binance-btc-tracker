import os
import csv
import json
import time
import logging
from datetime import datetime, timezone
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURATION (Env Vars) ---
REYA_SYMBOL = os.getenv("REYA_SYMBOL", "BTCRUSDPERP")
BINANCE_SYMBOL = os.getenv("BINANCE_SYMBOL", "BTCUSDT")
RESOLUTION = os.getenv("RESOLUTION", "1m")
ROWS = int(os.getenv("ROWS", "1440"))
OUT_DIR = os.getenv("OUT_DIR", "data")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
BACKOFF_SECONDS = float(os.getenv("BACKOFF_SECONDS", "1.0"))
BINANCE_BASE_URL = os.getenv("BINANCE_BASE_URL", "https://fapi.binance.com")

def create_session():
    session = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        read=MAX_RETRIES,
        connect=MAX_RETRIES,
        backoff_factor=BACKOFF_SECONDS,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def fetch_binance_data(session):
    url = f"{BINANCE_BASE_URL}/fapi/v1/markPriceKlines"
    params = {
        "symbol": BINANCE_SYMBOL,
        "interval": RESOLUTION,
        "limit": min(1500, ROWS + 10)
    }
    try:
        logging.info(f"Fetching Binance data from {url}...")
        resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        
        parsed_data = {}
        for row in data:
            ts_ms = int(row[0])
            close_price = float(row[4])
            
            dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            dt_minute = dt.replace(second=0, microsecond=0)
            
            parsed_data[dt_minute] = close_price
            
        logging.info(f"Successfully fetched {len(parsed_data)} candle(s) from Binance.")
        return parsed_data
    except Exception as e:
        status_code = getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
        if status_code == 451:
            logging.error(f"Binance API returned 451 Unavailable For Legal Reasons. Please configure BINANCE_BASE_URL to a valid proxy/regional endpoint. Detail: {e}")
        else:
            logging.error(f"Failed to fetch Binance data: {e}")
        return None

def fetch_reya_data(session):
    parsed_data = {}
    end_time_ms = int(time.time() * 1000)
    
    # Each request returns at most 200 candles. We need ROWS candles.
    batches_needed = (ROWS // 200) + 2
    
    for _ in range(batches_needed):
        url = f"https://api.reya.xyz/v2/candleHistory/{REYA_SYMBOL}/{RESOLUTION}"
        params = {"endTime": end_time_ms}
        try:
            logging.info(f"Fetching Reya data batch, endTime={end_time_ms}...")
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            
            if "t" in data and "c" in data:
                timestamps = data["t"]
                closes = data["c"]
                if not timestamps:
                    break
                    
                for i in range(len(timestamps)):
                    ts_s = int(timestamps[i])
                    if ts_s > 1e11:
                        ts_s = ts_s / 1000.0
                    dt = datetime.fromtimestamp(ts_s, tz=timezone.utc)
                    dt_minute = dt.replace(second=0, microsecond=0)
                    parsed_data[dt_minute] = float(closes[i])
                
                oldest_ts_s = min(timestamps)
                if oldest_ts_s > 1e11:
                    oldest_ts_s /= 1000.0
                end_time_ms = int(oldest_ts_s * 1000) - 60000
            else:
                logging.error(f"Unexpected Reya data dict keys: {data.keys()}")
                break
        except Exception as e:
            logging.error(f"Failed to fetch Reya data: {e}")
            break
            
        time.sleep(0.1)
        
    logging.info(f"Successfully fetched {len(parsed_data)} candle(s) from Reya.")
    return parsed_data

def main():
    session = create_session()
    
    binance_data = fetch_binance_data(session)
    reya_data = fetch_reya_data(session)
    
    if binance_data is None and reya_data is None:
        logging.error("Both data sources failed. Exiting with error.")
        exit(1)
        
    all_minutes = set()
    if binance_data: all_minutes.update(binance_data.keys())
    if reya_data: all_minutes.update(reya_data.keys())
    
    sorted_minutes = sorted(list(all_minutes), reverse=True)
    sorted_minutes = sorted_minutes[:ROWS]
    sorted_minutes.sort()
    
    updated_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    output_rows = []
    
    for dt_min in sorted_minutes:
        ts_utc = dt_min.strftime("%Y-%m-%d %H:%M:%SZ")
        binance_close = binance_data.get(dt_min) if binance_data else None
        reya_close = reya_data.get(dt_min) if reya_data else None
        
        abs_diff = None
        diff_pct = None
        
        if binance_close is not None and reya_close is not None:
            abs_diff = reya_close - binance_close
            diff_pct = (abs_diff / binance_close) * 100.0
            
        output_rows.append({
            "ts_utc": ts_utc,
            "binance_mark_close": binance_close,
            "reya_close": reya_close,
            "abs_diff": round(abs_diff, 4) if abs_diff is not None else None,
            "diff_pct": round(diff_pct, 6) if diff_pct is not None else None,
            "updated_at_utc": updated_at_utc
        })
        
    os.makedirs(OUT_DIR, exist_ok=True)
    
    csv_file = os.path.join(OUT_DIR, "btc_reya_vs_binance_1m.csv")
    json_file = os.path.join(OUT_DIR, "btc_reya_vs_binance_1m.json")
    
    logging.info(f"Writing {len(output_rows)} rows to {json_file}")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(output_rows, f, indent=2)
        
    logging.info(f"Writing {len(output_rows)} rows to {csv_file}")
    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["ts_utc", "binance_mark_close", "reya_close", "abs_diff", "diff_pct", "updated_at_utc"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
        
    logging.info("Run completed successfully.")

if __name__ == "__main__":
    main()
