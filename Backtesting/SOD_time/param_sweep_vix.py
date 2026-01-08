"""
SOD (7:30 CT) - VIX Level Regime Switching
- High Vol: VIX Open >= 20
- Low Vol: VIX Open < 20
- Uses VIX OPEN directly (available at 7:30 CT)
"""

import pandas as pd
import numpy as np
from datetime import time
from itertools import product
import os
from numba import njit

# =============================================================================
# CONFIGURATION - SOD (7:30 CT)
# =============================================================================

VIX_THRESHOLD = 20

LONG_BIAS_VALUES = [0, 1, 2, 3, 4, 5]
HIGH_VOL_COMBOS = [(1, d) for d in range(2, 6)] + [(2, d) for d in range(3, 8)]
LOW_VOL_COMBOS = [(3, d) for d in range(3, 11)] + [(4, d) for d in range(4, 11)] + [(5, d) for d in range(5, 11)]

LEVAMOUNT = 15
TARGET_TIME = time(7, 15)  # 7:15 bar for 7:30 execution
EXECUTION_TIME = "7:30 CT"
INITIAL_CAPITAL = 1_500_000
COMMISSION = 2.50
SLIPPAGE = 0.25
MULTIPLIER = 50
START_DATE = "2010-01-01"


def get_script_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return r"C:\Users\kshit\Desktop\Upwork\LOW_IBKR\Backtesting\SOD_time"


def get_data_dir():
    return os.path.dirname(get_script_dir())


@njit
def run_backtest_core(prices, indicators, long_bias, levamount, initial_capital, commission, slippage, multiplier):
    n = len(prices)
    cash = initial_capital
    position = 0
    entry_price = 0.0
    equity_arr = np.empty(n)
    trade_pnls = []

    for i in range(n):
        price = prices[i]
        indicator = indicators[i]

        if np.isnan(indicator):
            equity_arr[i] = cash + position * (price - entry_price) * multiplier
            continue

        raw_lev = indicator + long_bias
        net_lev = max(-levamount, min(levamount, raw_lev))
        unrealized = position * (price - entry_price) * multiplier
        equity = cash + unrealized
        target_value = net_lev * equity
        contract_value = price * multiplier
        target_qty = int(target_value // contract_value)
        trade_qty = target_qty - position

        if trade_qty != 0:
            fill_price = price + slippage if trade_qty > 0 else price - slippage
            abs_qty = abs(trade_qty)
            comm = abs_qty * commission
            pnl = 0.0
            old_pos = position
            new_pos = old_pos + trade_qty

            if old_pos == 0:
                entry_price = fill_price
            elif (new_pos > 0 and old_pos > 0) or (new_pos < 0 and old_pos < 0):
                if abs(new_pos) > abs(old_pos):
                    total_cost = abs(old_pos) * entry_price + abs_qty * fill_price
                    entry_price = total_cost / abs(new_pos)
                else:
                    pnl = abs_qty * (fill_price - entry_price) * multiplier
                    if old_pos < 0:
                        pnl = -pnl
            elif new_pos == 0:
                pnl = abs(old_pos) * (fill_price - entry_price) * multiplier
                if old_pos < 0:
                    pnl = -pnl
                entry_price = 0.0
            else:
                close_qty = abs(old_pos)
                pnl = close_qty * (fill_price - entry_price) * multiplier
                if old_pos < 0:
                    pnl = -pnl
                entry_price = fill_price

            position = new_pos
            cash += pnl - comm
            trade_pnls.append(pnl - comm)

        unrealized = position * (price - entry_price) * multiplier
        equity_arr[i] = cash + unrealized

    n_trades = len(trade_pnls)
    trade_pnl_arr = np.empty(n_trades)
    for j in range(n_trades):
        trade_pnl_arr[j] = trade_pnls[j]
    return equity_arr, trade_pnl_arr


def load_es_data(path, start_date):
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"].str.replace(r'[+-]\d{2}:\d{2}$', '', regex=True))
    df.set_index("date", inplace=True)
    return df[df.index >= start_date]


def load_vix_data(path):
    """Load VIX data - use OPEN directly for SOD (7:30 CT)"""
    df = pd.read_csv(path, sep=';')
    df['Date'] = pd.to_datetime(df['Date'], format='%d.%m.%Y')
    for col in ['Open', 'High', 'Low', 'Close']:
        df[col] = df[col].astype(str).str.replace(',', '.').astype(float)
    df.set_index('Date', inplace=True)
    df.sort_index(inplace=True)
    return df[['Open']]


def precompute_indicators(target_bars, days_values, offset_values):
    indicators = {}
    change = target_bars["change"].values
    for days in days_values:
        for offset in offset_values:
            if days <= offset:
                continue
            ind = np.full(len(change), np.nan)
            for i in range(days, len(change)):
                ind[i] = np.mean(change[i - days : i - offset + 1])
            indicators[(offset, days)] = ind
    return indicators


def precompute_vix_regime(target_bars, vix_data):
    """SOD: Use same-day VIX Open directly"""
    vix_open_series = vix_data['Open'].copy()
    vix_open_series.index = pd.to_datetime(vix_open_series.index.date)
    regime = np.zeros(len(target_bars), dtype=np.bool_)
    for i, dt in enumerate(target_bars.index):
        bar_date = pd.Timestamp(dt.date())
        if bar_date in vix_open_series.index:
            val = vix_open_series.loc[bar_date]
            if not pd.isna(val):
                regime[i] = val >= VIX_THRESHOLD
    return regime


def calc_metrics(equity_arr, trade_pnls, days_elapsed):
    final_equity = equity_arr[-1]
    total_return = (final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    cagr = ((final_equity / INITIAL_CAPITAL) ** (365 / days_elapsed) - 1) * 100 if final_equity > 0 and days_elapsed > 0 else -100
    running_max = np.maximum.accumulate(equity_arr)
    drawdowns = (running_max - equity_arr) / running_max * 100
    max_dd = np.nanmax(drawdowns)
    returns = np.diff(equity_arr) / equity_arr[:-1]
    sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
    n_trades = len(trade_pnls)
    if n_trades > 0:
        winners = trade_pnls[trade_pnls > 0]
        losers = trade_pnls[trade_pnls < 0]
        win_rate = len(winners) / n_trades * 100
        profit_factor = np.sum(winners) / abs(np.sum(losers)) if len(losers) > 0 and np.sum(losers) != 0 else np.inf
    else:
        win_rate = 0
        profit_factor = 0
    return {"final_equity": final_equity, "total_return_pct": total_return, "cagr_pct": cagr,
            "max_dd_pct": max_dd, "sharpe_ratio": sharpe, "total_trades": n_trades,
            "win_rate_pct": win_rate, "profit_factor": profit_factor}


def main():
    script_dir = get_script_dir()
    data_dir = get_data_dir()

    print("=" * 70)
    print(f"SOD VIX LEVEL REGIME SWITCHING ({EXECUTION_TIME})")
    print(f"High Vol = VIX Open >= {VIX_THRESHOLD}")
    print(f"VIX Source: Day OPEN (direct, no MA)")
    print("=" * 70)

    es_df = load_es_data(os.path.join(data_dir, "ES_15min.csv"), START_DATE)
    vix_df = load_vix_data(os.path.join(data_dir, "VIX_1990-2025.csv"))

    target_bars = es_df[es_df.index.time == TARGET_TIME].copy()
    target_bars["change"] = target_bars["close"] - target_bars["open"]
    prices = target_bars["close"].values

    print(f"Target bars ({TARGET_TIME}): {len(target_bars)}")

    high_vol_mask = precompute_vix_regime(target_bars, vix_df)
    low_vol_mask = ~high_vol_mask
    print(f"High vol bars: {high_vol_mask.sum()}, Low vol bars: {low_vol_mask.sum()}")

    all_days = list(set([d for _, d in LOW_VOL_COMBOS + HIGH_VOL_COMBOS]))
    all_offsets = list(set([o for o, _ in LOW_VOL_COMBOS + HIGH_VOL_COMBOS]))
    indicators = precompute_indicators(target_bars, all_days, all_offsets)

    all_combos = list(product(LONG_BIAS_VALUES, LOW_VOL_COMBOS, HIGH_VOL_COMBOS))
    total = len(all_combos)
    print(f"\nTesting {total} combinations...")

    days_elapsed = (target_bars.index[-1] - target_bars.index[0]).days
    results = []

    for i, (long_bias, (low_offset, low_days), (high_offset, high_days)) in enumerate(all_combos):
        low_ind = indicators.get((low_offset, low_days))
        high_ind = indicators.get((high_offset, high_days))
        if low_ind is None or high_ind is None:
            continue

        combined_ind = np.where(high_vol_mask, high_ind, low_ind)
        equity_arr, trade_pnls = run_backtest_core(prices, combined_ind, long_bias,
                                                    LEVAMOUNT, INITIAL_CAPITAL, COMMISSION, SLIPPAGE, MULTIPLIER)

        metrics = calc_metrics(equity_arr, trade_pnls, days_elapsed)
        metrics.update({"long_bias": long_bias, "low_vol_offset": low_offset, "low_vol_days": low_days,
                       "high_vol_offset": high_offset, "high_vol_days": high_days,
                       "low_vol_bars": int(low_vol_mask.sum()), "high_vol_bars": int(high_vol_mask.sum())})
        results.append(metrics)

        if (i + 1) % 200 == 0 or (i + 1) == total:
            print(f"Progress: {i+1}/{total}")

    results_df = pd.DataFrame(results).sort_values("cagr_pct", ascending=False)

    output_dir = os.path.join(script_dir, "results")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "param_sweep_vix_results.csv")
    results_df.to_csv(output_path, index=False)
    print(f"\nSaved to: {output_path}")

    print("\n" + "=" * 90)
    print("TOP 10 VIX LEVEL REGIME-SWITCHING COMBINATIONS")
    print("=" * 90)

    for idx, (_, row) in enumerate(results_df.head(10).iterrows()):
        print(f"\n#{idx+1}: LongBias={row['long_bias']}")
        print(f"    LowVol: Offset={row['low_vol_offset']}, Days={row['low_vol_days']}  |  HighVol: Offset={row['high_vol_offset']}, Days={row['high_vol_days']}")
        print(f"    CAGR: {row['cagr_pct']:.2f}%  |  MaxDD: {row['max_dd_pct']:.1f}%  |  Sharpe: {row['sharpe_ratio']:.2f}")

    profitable = len(results_df[results_df['cagr_pct'] > 0])
    print(f"\nSUMMARY: {profitable}/{len(results_df)} profitable | Best CAGR: {results_df['cagr_pct'].max():.2f}%")

    return results_df


if __name__ == "__main__":
    results = main()
