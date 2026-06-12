"""Download historical market data and save it to data/{SYMBOL}.csv."""

import os
import datetime
import sys

import yfinance as yf

DATA_DIR = "data"


def download_symbol(symbol: str = "SPY", start_date: str = "2000-01-01", end_date: str = None) -> str:
    symbol = symbol.upper()

    if end_date is None:
        end_date = datetime.date.today().isoformat()

    os.makedirs(DATA_DIR, exist_ok=True)

    output_file = os.path.join(DATA_DIR, f"{symbol}.csv")

    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_date, end=end_date, auto_adjust=False)

    if df.empty:
        raise ValueError(f"No data downloaded for {symbol} from {start_date} to {end_date}.")

    df = df[["Open", "High", "Low", "Close", "Volume"]]
    df.index.name = "Date"
    df.to_csv(output_file, index=True, date_format="%Y-%m-%d")

    print(f"Saved {symbol} data to {output_file} ({len(df)} rows)")
    return output_file


def main() -> None:
    symbol = "SPY"

    if len(sys.argv) > 1:
        symbol = sys.argv[1]

    download_symbol(symbol)


if __name__ == "__main__":
    main()