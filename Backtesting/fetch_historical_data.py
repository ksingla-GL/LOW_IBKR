"""
ES Futures Historical Data Fetcher
Pulls max available 15-min bars from Interactive Brokers and saves to CSV

Note: ContFuture only allows endDateTime='' (now), so we request max available.
IB typically provides ~1 year of 15-min data for continuous futures.
"""

import time
from datetime import datetime
from ib_insync import IB, ContFuture
import pandas as pd
import os

# Configuration
HOST = "127.0.0.1"
PORT = 7497  # Paper trading port
CLIENT_ID = 10

SYMBOL = "ES"
EXCHANGE = "CME"
CURRENCY = "USD"
BAR_SIZE = "15 mins"
WHAT_TO_SHOW = "TRADES"

OUTPUT_FILE = "ES_15min.csv"


def fetch_historical_data():
    """Fetch max available 15-min ES futures data"""

    ib = IB()

    print(f"Connecting to TWS at {HOST}:{PORT}...")
    try:
        ib.connect(HOST, PORT, clientId=CLIENT_ID)
        print("Connected successfully!")
    except Exception as e:
        print(f"Connection failed: {e}")
        return None

    # Create continuous futures contract
    contract = ContFuture(symbol=SYMBOL, exchange=EXCHANGE, currency=CURRENCY)
    ib.qualifyContracts(contract)
    print(f"Contract: {contract.localSymbol}")

    # For ContFuture, we can only use endDateTime='' (now)
    # Try progressively larger durations to find max available
    durations = ['2 Y', '1 Y', '6 M', '3 M', '1 M']
    bars = None

    for duration in durations:
        print(f"\nTrying duration: {duration}...", end=" ", flush=True)
        try:
            bars = ib.reqHistoricalData(
                contract,
                endDateTime='',  # Must be empty for ContFuture
                durationStr=duration,
                barSizeSetting=BAR_SIZE,
                whatToShow=WHAT_TO_SHOW,
                useRTH=False,
                formatDate=1,
                timeout=120
            )
            if bars and len(bars) > 0:
                print(f"SUCCESS! Got {len(bars):,} bars")
                print(f"  Range: {bars[0].date} to {bars[-1].date}")
                break
            else:
                print("no data")
        except Exception as e:
            error_msg = str(e)
            if "pacing" in error_msg.lower():
                print("pacing violation - waiting 10s...")
                time.sleep(10)
            else:
                print(f"failed: {e}")

    ib.disconnect()
    print("\nDisconnected from TWS")

    if not bars:
        print("No data retrieved!")
        return None

    # Convert to DataFrame
    print(f"\nProcessing {len(bars):,} bars...")
    df = pd.DataFrame([{
        'date': bar.date,
        'open': bar.open,
        'high': bar.high,
        'low': bar.low,
        'close': bar.close,
        'volume': bar.volume,
        'average': bar.average,
        'barCount': bar.barCount
    } for bar in bars])

    df['date'] = pd.to_datetime(df['date'])
    df = df.drop_duplicates(subset='date')
    df = df.sort_values('date')
    df.set_index('date', inplace=True)

    # Save to CSV
    output_path = os.path.join(os.path.dirname(__file__), OUTPUT_FILE)
    df.to_csv(output_path)

    print(f"\nSaved to: {output_path}")
    print(f"Total bars: {len(df):,}")
    print(f"Date range: {df.index[0]} to {df.index[-1]}")
    days_covered = (df.index[-1] - df.index[0]).days
    print(f"Days covered: {days_covered}")
    print(f"File size: {os.path.getsize(output_path) / 1024 / 1024:.2f} MB")

    print("\n--- Last 5 bars ---")
    print(df.tail())

    return df


if __name__ == "__main__":
    print("=" * 60)
    print("ES Futures Historical Data Fetcher")
    print("=" * 60)
    fetch_historical_data()
