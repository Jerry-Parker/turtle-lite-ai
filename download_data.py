"""Download historical SPY data and save it to data/SPY.csv."""

import os
import datetime

import yfinance as yf

DATA_DIR = "data"
OUTPUT_FILE = os.path.join(DATA_DIR, "SPY.csv")


def download_spy(start_date: str = "2000-01-01", end_date: str = None) -> None:
    if end_date is None:
        end_date = datetime.date.today().isoformat()

    os.makedirs(DATA_DIR, exist_ok=True)

    ticker = yf.Ticker("SPY")
    df = ticker.history(start=start_date, end=end_date, auto_adjust=False)

    if df.empty:
        raise ValueError(f"No data downloaded for SPY from {start_date} to {end_date}.")

    df = df[["Open", "High", "Low", "Close", "Volume"]]
    df.index.name = "Date"
    df.to_csv(OUTPUT_FILE, index=True, date_format="%Y-%m-%d")
    print(f"Saved SPY data to {OUTPUT_FILE} ({len(df)} rows)")


def main() -> None:
    download_spy()


if __name__ == "__main__":
    main()