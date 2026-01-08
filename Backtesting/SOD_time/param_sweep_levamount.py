"""
SOD (7:30 CT) - LEVAMOUNT Sweep
Tests different max leverage values to find optimal risk/return trade-off
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

# Sweep LEVAMOUNT values
LEVAMOUNT_VALUES = [5, 8, 10, 12, 15, 18, 20]

# Test with multiple long bias values
LONG_BIAS_VALUES = [2, 3, 4]

# Use best performing indicator combos from previous tests
HIGH_VOL_COMBOS = [(1, 5)]  # Best: Offset=1, Days=5
LOW_VOL_COMBOS = [(3, 9), (4, 9), (5, 9), (3, 10), (4, 10)]  # Top performers

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
    print(f"SOD LEVAMOUNT SWEEP ({EXECUTION_TIME})")
    print(f"Testing LEVAMOUNT: {LEVAMOUNT_VALUES}")
    print(f"Long Bias: {LONG_BIAS_VALUES}")
    print(f"VIX Threshold: {VIX_THRESHOLD}")
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

    all_combos = list(product(LEVAMOUNT_VALUES, LONG_BIAS_VALUES, LOW_VOL_COMBOS, HIGH_VOL_COMBOS))
    total = len(all_combos)
    print(f"\nTesting {total} combinations...")

    days_elapsed = (target_bars.index[-1] - target_bars.index[0]).days
    results = []

    for i, (levamount, long_bias, (low_offset, low_days), (high_offset, high_days)) in enumerate(all_combos):
        low_ind = indicators.get((low_offset, low_days))
        high_ind = indicators.get((high_offset, high_days))
        if low_ind is None or high_ind is None:
            continue

        combined_ind = np.where(high_vol_mask, high_ind, low_ind)
        equity_arr, trade_pnls = run_backtest_core(prices, combined_ind, long_bias,
                                                    levamount, INITIAL_CAPITAL, COMMISSION, SLIPPAGE, MULTIPLIER)

        metrics = calc_metrics(equity_arr, trade_pnls, days_elapsed)
        metrics.update({
            "levamount": levamount,
            "long_bias": long_bias,
            "low_vol_offset": low_offset,
            "low_vol_days": low_days,
            "high_vol_offset": high_offset,
            "high_vol_days": high_days,
        })
        results.append(metrics)

    results_df = pd.DataFrame(results).sort_values("cagr_pct", ascending=False)

    output_dir = os.path.join(script_dir, "results")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "param_sweep_levamount_results.csv")
    results_df.to_csv(output_path, index=False)
    print(f"\nSaved to: {output_path}")

    # Summary by LEVAMOUNT
    print("\n" + "=" * 90)
    print("BEST RESULTS BY LEVAMOUNT")
    print("=" * 90)
    print(f"{'LEVAMOUNT':<12} {'Best CAGR':<12} {'Max DD':<12} {'Sharpe':<10} {'Long Bias':<12} {'Config'}")
    print("-" * 90)

    for lev in LEVAMOUNT_VALUES:
        subset = results_df[results_df['levamount'] == lev]
        best = subset.loc[subset['cagr_pct'].idxmax()]
        config = f"LV:O{int(best['low_vol_offset'])}/D{int(best['low_vol_days'])}"
        print(f"{int(lev):<12} {best['cagr_pct']:.2f}%{'':<6} {best['max_dd_pct']:.1f}%{'':<6} {best['sharpe_ratio']:.2f}{'':<6} {int(best['long_bias']):<12} {config}")

    # Summary by LEVAMOUNT and Long Bias
    print("\n" + "=" * 90)
    print("CAGR BY LEVAMOUNT AND LONG BIAS (Best indicator combo for each)")
    print("=" * 90)

    pivot_cagr = results_df.groupby(['levamount', 'long_bias'])['cagr_pct'].max().unstack()
    pivot_dd = results_df.groupby(['levamount', 'long_bias'])['max_dd_pct'].min().unstack()

    print("\nCAGR (%):")
    print(pivot_cagr.round(1).to_string())

    print("\nMax DD (%):")
    print(pivot_dd.round(1).to_string())

    # Risk-adjusted view
    print("\n" + "=" * 90)
    print("RISK-ADJUSTED VIEW: CAGR / Max DD Ratio")
    print("=" * 90)

    results_df['cagr_dd_ratio'] = results_df['cagr_pct'] / results_df['max_dd_pct']
    best_ratio = results_df.loc[results_df['cagr_dd_ratio'].idxmax()]

    print(f"\nBest CAGR/DD Ratio: {best_ratio['cagr_dd_ratio']:.3f}")
    print(f"  LEVAMOUNT={int(best_ratio['levamount'])}, LongBias={int(best_ratio['long_bias'])}")
    print(f"  CAGR={best_ratio['cagr_pct']:.2f}%, MaxDD={best_ratio['max_dd_pct']:.1f}%")

    return results_df


if __name__ == "__main__":
    results = main()
