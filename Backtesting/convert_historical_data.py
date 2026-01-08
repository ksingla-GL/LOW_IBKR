"""
Convert ES_15min_2007-2025.txt to CSV format for backtesting

Input format:  DD/MM/YYYY;HH:MM:SS;Open;High;Low;Close;Volume
Output format: date,open,high,low,close,volume
"""

import os

INPUT_FILE = "ES_15min_2007-2025.txt"
OUTPUT_FILE = "ES_15min.csv"


def convert():
    script_dir = os.path.dirname(__file__)
    input_path = os.path.join(script_dir, INPUT_FILE)
    output_path = os.path.join(script_dir, OUTPUT_FILE)

    print(f"Reading: {input_path}")

    with open(input_path, 'r') as f:
        lines = f.readlines()

    print(f"Total lines: {len(lines):,}")

    converted = []
    errors = 0

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        try:
            parts = line.split(';')
            if len(parts) < 7:
                errors += 1
                continue

            date_str, time_str, open_, high, low, close, volume = parts[:7]

            # Convert DD/MM/YYYY to YYYY-MM-DD
            day, month, year = date_str.split('/')
            new_date = f"{year}-{month}-{day} {time_str}"

            converted.append(f"{new_date},{open_},{high},{low},{close},{volume}")

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error line {i+1}: {line[:50]}... -> {e}")

    print(f"Converted: {len(converted):,} rows")
    if errors:
        print(f"Errors: {errors}")

    # Write output
    with open(output_path, 'w') as f:
        f.write("date,open,high,low,close,volume\n")
        f.write('\n'.join(converted))

    print(f"\nSaved to: {output_path}")
    print(f"Date range: {converted[0].split(',')[0]} to {converted[-1].split(',')[0]}")


if __name__ == "__main__":
    convert()
