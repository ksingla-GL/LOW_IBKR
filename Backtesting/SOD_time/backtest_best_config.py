"""
SOD (7:30 CT) - Best Configuration Detailed Backtest
Config: LEVAMOUNT=5, Long Bias=3, VIX Threshold=20
High Vol (VIX>=20): Offset=1, Days=5
Low Vol (VIX<20): Offset=5, Days=9
"""

import pandas as pd
import numpy as np
from datetime import time
import os
import matplotlib.pyplot as plt
from numba import njit

# =============================================================================
# BEST CONFIGURATION
# =============================================================================

LEVAMOUNT = 3
LONG_BIAS = 3
VIX_THRESHOLD = 20

# High Vol params (VIX >= 20)
HIGH_VOL_OFFSET = 1
HIGH_VOL_DAYS = 5

# Low Vol params (VIX < 20)
LOW_VOL_OFFSET = 5
LOW_VOL_DAYS = 9

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
    positions_arr = np.empty(n)
    trade_pnls = []
    trade_indices = []

    for i in range(n):
        price = prices[i]
        indicator = indicators[i]

        if np.isnan(indicator):
            equity_arr[i] = cash + position * (price - entry_price) * multiplier
            positions_arr[i] = position
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
            trade_indices.append(i)

        unrealized = position * (price - entry_price) * multiplier
        equity_arr[i] = cash + unrealized
        positions_arr[i] = position

    n_trades = len(trade_pnls)
    trade_pnl_arr = np.empty(n_trades)
    trade_idx_arr = np.empty(n_trades, dtype=np.int64)
    for j in range(n_trades):
        trade_pnl_arr[j] = trade_pnls[j]
        trade_idx_arr[j] = trade_indices[j]
    return equity_arr, positions_arr, trade_pnl_arr, trade_idx_arr


def load_es_data(path, start_date):
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"].str.replace(r'[+-]\d{2}:\d{2}$', '', regex=True))
    df.set_index("date", inplace=True)
    return df[df.index >= start_date]


def load_vix_data(path):
    df = pd.read_csv(path, sep=';')
    df['Date'] = pd.to_datetime(df['Date'], format='%d.%m.%Y')
    for col in ['Open', 'High', 'Low', 'Close']:
        df[col] = df[col].astype(str).str.replace(',', '.').astype(float)
    df.set_index('Date', inplace=True)
    df.sort_index(inplace=True)
    return df[['Open']]


def compute_indicator(change, days, offset):
    ind = np.full(len(change), np.nan)
    for i in range(days, len(change)):
        ind[i] = np.mean(change[i - days : i - offset + 1])
    return ind


def compute_vix_regime(target_bars, vix_data, threshold):
    vix_open_series = vix_data['Open'].copy()
    vix_open_series.index = pd.to_datetime(vix_open_series.index.date)
    regime = np.zeros(len(target_bars), dtype=np.bool_)
    vix_values = np.full(len(target_bars), np.nan)

    for i, dt in enumerate(target_bars.index):
        bar_date = pd.Timestamp(dt.date())
        if bar_date in vix_open_series.index:
            val = vix_open_series.loc[bar_date]
            if not pd.isna(val):
                vix_values[i] = val
                regime[i] = val >= threshold
    return regime, vix_values


def calc_drawdown(equity_arr):
    running_max = np.maximum.accumulate(equity_arr)
    drawdowns = (running_max - equity_arr) / running_max * 100
    return drawdowns


def main():
    script_dir = get_script_dir()
    data_dir = get_data_dir()

    print("=" * 70)
    print(f"SOD BEST CONFIG DETAILED BACKTEST ({EXECUTION_TIME})")
    print("=" * 70)
    print(f"LEVAMOUNT: {LEVAMOUNT}")
    print(f"Long Bias: {LONG_BIAS}")
    print(f"VIX Threshold: {VIX_THRESHOLD}")
    print(f"High Vol (VIX>={VIX_THRESHOLD}): Offset={HIGH_VOL_OFFSET}, Days={HIGH_VOL_DAYS}")
    print(f"Low Vol (VIX<{VIX_THRESHOLD}): Offset={LOW_VOL_OFFSET}, Days={LOW_VOL_DAYS}")
    print("=" * 70)

    # Load data
    es_df = load_es_data(os.path.join(data_dir, "ES_15min.csv"), START_DATE)
    vix_df = load_vix_data(os.path.join(data_dir, "VIX_1990-2025.csv"))

    # Get target bars
    target_bars = es_df[es_df.index.time == TARGET_TIME].copy()
    target_bars["change"] = target_bars["close"] - target_bars["open"]
    prices = target_bars["close"].values

    print(f"\nTarget bars ({TARGET_TIME}): {len(target_bars)}")
    print(f"Date range: {target_bars.index[0].date()} to {target_bars.index[-1].date()}")

    # Compute VIX regime
    high_vol_mask, vix_values = compute_vix_regime(target_bars, vix_df, VIX_THRESHOLD)
    low_vol_mask = ~high_vol_mask
    print(f"High vol bars: {high_vol_mask.sum()} ({high_vol_mask.sum()/len(target_bars)*100:.1f}%)")
    print(f"Low vol bars: {low_vol_mask.sum()} ({low_vol_mask.sum()/len(target_bars)*100:.1f}%)")

    # Compute indicators
    change = target_bars["change"].values
    high_vol_ind = compute_indicator(change, HIGH_VOL_DAYS, HIGH_VOL_OFFSET)
    low_vol_ind = compute_indicator(change, LOW_VOL_DAYS, LOW_VOL_OFFSET)
    combined_ind = np.where(high_vol_mask, high_vol_ind, low_vol_ind)

    # Run backtest
    equity_arr, positions_arr, trade_pnls, trade_indices = run_backtest_core(
        prices, combined_ind, LONG_BIAS, LEVAMOUNT, INITIAL_CAPITAL, COMMISSION, SLIPPAGE, MULTIPLIER
    )

    # Calculate metrics
    days_elapsed = (target_bars.index[-1] - target_bars.index[0]).days
    final_equity = equity_arr[-1]
    total_return = (final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    cagr = ((final_equity / INITIAL_CAPITAL) ** (365 / days_elapsed) - 1) * 100
    drawdowns = calc_drawdown(equity_arr)
    max_dd = np.nanmax(drawdowns)

    returns = np.diff(equity_arr) / equity_arr[:-1]
    sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252)

    n_trades = len(trade_pnls)
    winners = trade_pnls[trade_pnls > 0]
    losers = trade_pnls[trade_pnls < 0]
    win_rate = len(winners) / n_trades * 100 if n_trades > 0 else 0
    profit_factor = np.sum(winners) / abs(np.sum(losers)) if len(losers) > 0 else np.inf
    avg_win = np.mean(winners) if len(winners) > 0 else 0
    avg_loss = np.mean(losers) if len(losers) > 0 else 0

    # Print results
    print("\n" + "=" * 70)
    print("PERFORMANCE SUMMARY")
    print("=" * 70)
    print(f"Initial Capital:    ${INITIAL_CAPITAL:,.0f}")
    print(f"Final Equity:       ${final_equity:,.0f}")
    print(f"Total Return:       {total_return:.1f}%")
    print(f"CAGR:               {cagr:.2f}%")
    print(f"Max Drawdown:       {max_dd:.1f}%")
    print(f"Sharpe Ratio:       {sharpe:.2f}")
    print(f"Total Trades:       {n_trades}")
    print(f"Win Rate:           {win_rate:.1f}%")
    print(f"Profit Factor:      {profit_factor:.2f}")
    print(f"Avg Win:            ${avg_win:,.0f}")
    print(f"Avg Loss:           ${avg_loss:,.0f}")

    # Period analysis
    print("\n" + "=" * 70)
    print("PERFORMANCE BY PERIOD")
    print("=" * 70)

    equity_df = pd.DataFrame({
        'date': target_bars.index,
        'equity': equity_arr,
        'position': positions_arr,
        'vix': vix_values,
        'high_vol': high_vol_mask
    }).set_index('date')

    # Yearly performance
    equity_df['year'] = equity_df.index.year
    yearly = equity_df.groupby('year').agg({
        'equity': ['first', 'last']
    })
    yearly.columns = ['start_eq', 'end_eq']
    yearly['return_pct'] = (yearly['end_eq'] - yearly['start_eq']) / yearly['start_eq'] * 100

    print("\nYearly Returns:")
    print("-" * 40)
    for year, row in yearly.iterrows():
        print(f"{year}: {row['return_pct']:+.1f}%")

    # Recent performance
    print("\n" + "=" * 70)
    print("RECENT PERFORMANCE")
    print("=" * 70)

    for years, label in [(5, "Last 5 Years"), (2, "Last 2 Years"), (1, "Last 1 Year")]:
        cutoff = target_bars.index[-1] - pd.DateOffset(years=years)
        mask = target_bars.index >= cutoff
        if mask.sum() > 0:
            period_equity = equity_arr[mask]
            period_return = (period_equity[-1] - period_equity[0]) / period_equity[0] * 100
            period_days = (target_bars.index[mask][-1] - target_bars.index[mask][0]).days
            period_cagr = ((period_equity[-1] / period_equity[0]) ** (365 / period_days) - 1) * 100 if period_days > 0 else 0
            period_dd = np.nanmax(calc_drawdown(period_equity))
            print(f"{label}: Return={period_return:.1f}%, CAGR={period_cagr:.1f}%, MaxDD={period_dd:.1f}%")

    # Save equity curve
    output_dir = os.path.join(script_dir, "results")
    os.makedirs(output_dir, exist_ok=True)

    equity_df.to_csv(os.path.join(output_dir, "best_config_equity.csv"))
    print(f"\nEquity curve saved to: {output_dir}/best_config_equity.csv")

    # Create chart
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    # Equity curve
    axes[0].plot(equity_df.index, equity_df['equity'] / 1e6, 'b-', linewidth=1)
    axes[0].set_ylabel('Equity ($M)')
    axes[0].set_title(f'SOD Best Config: LEVAMOUNT={LEVAMOUNT}, Bias={LONG_BIAS}, VIX Threshold={VIX_THRESHOLD}\n'
                      f'CAGR={cagr:.1f}%, Max DD={max_dd:.1f}%, Sharpe={sharpe:.2f}')
    axes[0].grid(True, alpha=0.3)
    axes[0].axhline(y=INITIAL_CAPITAL/1e6, color='gray', linestyle='--', alpha=0.5)

    # Drawdown
    axes[1].fill_between(equity_df.index, 0, -drawdowns, color='red', alpha=0.3)
    axes[1].set_ylabel('Drawdown (%)')
    axes[1].set_ylim(-100, 0)
    axes[1].grid(True, alpha=0.3)

    # Position
    axes[2].plot(equity_df.index, equity_df['position'], 'g-', linewidth=0.5, alpha=0.7)
    axes[2].axhline(y=0, color='black', linestyle='-', alpha=0.3)
    axes[2].set_ylabel('Position (contracts)')
    axes[2].set_xlabel('Date')
    axes[2].grid(True, alpha=0.3)

    plt.tight_layout()
    chart_path = os.path.join(output_dir, "best_config_chart.png")
    plt.savefig(chart_path, dpi=150)
    print(f"Chart saved to: {chart_path}")
    plt.close()

    # Position statistics
    print("\n" + "=" * 70)
    print("POSITION STATISTICS")
    print("=" * 70)
    print(f"Max Long Position:  {positions_arr.max():.0f} contracts")
    print(f"Max Short Position: {positions_arr.min():.0f} contracts")
    print(f"Avg Position:       {np.mean(positions_arr):.1f} contracts")
    print(f"% Time Long:        {(positions_arr > 0).sum() / len(positions_arr) * 100:.1f}%")
    print(f"% Time Short:       {(positions_arr < 0).sum() / len(positions_arr) * 100:.1f}%")
    print(f"% Time Flat:        {(positions_arr == 0).sum() / len(positions_arr) * 100:.1f}%")

    return equity_df


if __name__ == "__main__":
    results = main()
