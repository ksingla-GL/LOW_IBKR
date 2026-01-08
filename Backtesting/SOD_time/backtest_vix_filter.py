"""
SOD (Start of Day) VIX Filter Strategy
Execution Time: 7:30 CT (uses 7:15 bar)
VIX: Uses day OPEN (VIX opens at 7:30 CT - same time as trade)
"""

import pandas as pd
import numpy as np
from datetime import time
import matplotlib.pyplot as plt
import os
import sys
from numba import njit

# =============================================================================
# CONFIGURATION - SOD (7:30 CT execution)
# =============================================================================

# Best VIX ROC params
LONG_BIAS = 4
LOW_VOL_OFFSET = 3
LOW_VOL_DAYS = 10
HIGH_VOL_OFFSET = 2
HIGH_VOL_DAYS = 4

VIX_ROC_THRESHOLD = 0.20
VIX_ROC_PERIOD = 5

# VIX filter - go flat when VIX above this
VIX_FILTER_THRESHOLD = 20

LEVAMOUNT = 15
INITIAL_CAPITAL = 1_500_000
COMMISSION = 2.50
SLIPPAGE = 0.25
MULTIPLIER = 50
START_DATE = "2010-01-01"

# SOD specific: 7:30 execution -> 7:15 bar
TARGET_TIME = time(7, 15)
EXECUTION_TIME = "7:30 CT"


def get_script_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return r"C:\Users\kshit\Desktop\Upwork\LOW_IBKR\Backtesting\SOD_time"


def get_data_dir():
    """Parent directory where data files are stored"""
    return os.path.dirname(get_script_dir())


# =============================================================================
# NUMBA BACKTEST
# =============================================================================

@njit
def run_backtest_core(
    prices: np.ndarray,
    indicators: np.ndarray,
    vix_filter: np.ndarray,
    long_bias: float,
    levamount: float,
    initial_capital: float,
    commission: float,
    slippage: float,
    multiplier: float
) -> tuple:
    n = len(prices)
    cash = initial_capital
    position = 0
    entry_price = 0.0

    equity_arr = np.empty(n)
    trade_pnls = []
    positions_arr = np.empty(n)

    for i in range(n):
        price = prices[i]
        indicator = indicators[i]
        can_trade = vix_filter[i]

        if not can_trade or np.isnan(indicator):
            target_qty = 0
        else:
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
        positions_arr[i] = position

    n_trades = len(trade_pnls)
    trade_pnl_arr = np.empty(n_trades)
    for j in range(n_trades):
        trade_pnl_arr[j] = trade_pnls[j]

    return equity_arr, trade_pnl_arr, positions_arr


# =============================================================================
# DATA LOADING
# =============================================================================

def load_es_data(path: str, start_date: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"].str.replace(r'[+-]\d{2}:\d{2}$', '', regex=True))
    df.set_index("date", inplace=True)
    return df[df.index >= start_date]


def load_vix_data(path: str) -> pd.DataFrame:
    """Load VIX data and compute ROC using OPEN prices for SOD"""
    df = pd.read_csv(path, sep=';')
    df['Date'] = pd.to_datetime(df['Date'], format='%d.%m.%Y')
    for col in ['Open', 'High', 'Low', 'Close']:
        df[col] = df[col].astype(str).str.replace(',', '.').astype(float)
    df.set_index('Date', inplace=True)
    df.sort_index(inplace=True)
    # SOD: Use OPEN for ROC calculation
    df['vix_roc'] = df['Open'].pct_change(periods=VIX_ROC_PERIOD)
    return df


# =============================================================================
# COMPUTE
# =============================================================================

def compute_indicator(change: np.ndarray, days: int, offset: int) -> np.ndarray:
    ind = np.full(len(change), np.nan)
    for i in range(days, len(change)):
        ind[i] = np.mean(change[i - days : i - offset + 1])
    return ind


def compute_vix_roc_regime(target_bars: pd.DataFrame, vix_data: pd.DataFrame) -> np.ndarray:
    """SOD: Use same-day VIX Open for ROC (trade at 7:30 CT, VIX opens at 7:30 CT)"""
    vix_roc_series = vix_data['vix_roc'].copy()
    vix_roc_series.index = pd.to_datetime(vix_roc_series.index.date)

    regime = np.zeros(len(target_bars), dtype=np.bool_)
    for i, dt in enumerate(target_bars.index):
        bar_date = pd.Timestamp(dt.date())
        if bar_date in vix_roc_series.index:
            val = vix_roc_series.loc[bar_date]
            if not pd.isna(val):
                regime[i] = val > VIX_ROC_THRESHOLD
    return regime


def compute_vix_filter(target_bars: pd.DataFrame, vix_data: pd.DataFrame) -> tuple:
    """SOD: Use same-day VIX OPEN for filter (trade at 7:30 CT, VIX opens at 7:30 CT)"""
    vix_open = vix_data['Open'].copy()
    vix_open.index = pd.to_datetime(vix_open.index.date)

    can_trade = np.ones(len(target_bars), dtype=np.bool_)
    vix_values = np.full(len(target_bars), np.nan)

    for i, dt in enumerate(target_bars.index):
        bar_date = pd.Timestamp(dt.date())
        if bar_date in vix_open.index:
            val = vix_open.loc[bar_date]
            if not pd.isna(val):
                vix_values[i] = val
                can_trade[i] = val < VIX_FILTER_THRESHOLD

    return can_trade, vix_values


def calc_period_stats(equity_df: pd.DataFrame, start_date: str, end_date: str, period_name: str) -> dict:
    mask = (equity_df.index >= start_date) & (equity_df.index <= end_date)
    period_df = equity_df[mask]

    if len(period_df) < 2:
        return None

    start_equity = period_df['equity'].iloc[0]
    end_equity = period_df['equity'].iloc[-1]
    days = (period_df.index[-1] - period_df.index[0]).days

    total_return = (end_equity - start_equity) / start_equity * 100
    cagr = ((end_equity / start_equity) ** (365 / days) - 1) * 100 if days > 0 else 0

    running_max = period_df['equity'].cummax()
    drawdown = (running_max - period_df['equity']) / running_max * 100
    max_dd = drawdown.max()

    returns = period_df['equity'].pct_change().dropna()
    sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0

    return {
        'period': period_name,
        'start_date': period_df.index[0].strftime('%Y-%m-%d'),
        'end_date': period_df.index[-1].strftime('%Y-%m-%d'),
        'start_equity': start_equity,
        'end_equity': end_equity,
        'return_pct': total_return,
        'cagr_pct': cagr,
        'max_dd_pct': max_dd,
        'sharpe': sharpe
    }


# =============================================================================
# MAIN
# =============================================================================

def main():
    script_dir = get_script_dir()
    data_dir = get_data_dir()

    print("=" * 70)
    print("SOD (START OF DAY) VIX FILTER STRATEGY")
    print(f"Execution Time: {EXECUTION_TIME} (uses {TARGET_TIME} bar)")
    print(f"VIX Source: Day OPEN (VIX opens at 7:30 CT)")
    print(f"VIX Filter: Only trade when VIX Open < {VIX_FILTER_THRESHOLD}")
    print("=" * 70)

    # Load data from parent directory
    print("\nLoading data...")
    es_df = load_es_data(os.path.join(data_dir, "ES_15min.csv"), START_DATE)
    vix_df = load_vix_data(os.path.join(data_dir, "VIX_1990-2025.csv"))

    # Filter to target time (7:15 bar for 7:30 execution)
    target_bars = es_df[es_df.index.time == TARGET_TIME].copy()
    target_bars["change"] = target_bars["close"] - target_bars["open"]
    prices = target_bars["close"].values

    print(f"Target bars ({TARGET_TIME}): {len(target_bars)}")

    # Compute regime for indicator selection
    high_vol_mask = compute_vix_roc_regime(target_bars, vix_df)

    # Compute VIX filter using VIX Open
    vix_filter, vix_values = compute_vix_filter(target_bars, vix_df)
    trading_days = vix_filter.sum()
    flat_days = (~vix_filter).sum()
    print(f"Trading days (VIX Open < {VIX_FILTER_THRESHOLD}): {trading_days} ({trading_days/len(vix_filter)*100:.1f}%)")
    print(f"Flat days (VIX Open >= {VIX_FILTER_THRESHOLD}): {flat_days} ({flat_days/len(vix_filter)*100:.1f}%)")

    # Compute indicators
    change = target_bars["change"].values
    low_vol_ind = compute_indicator(change, LOW_VOL_DAYS, LOW_VOL_OFFSET)
    high_vol_ind = compute_indicator(change, HIGH_VOL_DAYS, HIGH_VOL_OFFSET)
    combined_ind = np.where(high_vol_mask, high_vol_ind, low_vol_ind)

    # Run backtest WITH VIX filter
    print("\nRunning backtest with VIX filter...")
    equity_arr, trade_pnls, positions = run_backtest_core(
        prices, combined_ind, vix_filter, LONG_BIAS,
        LEVAMOUNT, INITIAL_CAPITAL, COMMISSION, SLIPPAGE, MULTIPLIER
    )

    # Also run WITHOUT filter for comparison
    print("Running backtest WITHOUT VIX filter (comparison)...")
    no_filter = np.ones(len(target_bars), dtype=np.bool_)
    equity_no_filter, _, _ = run_backtest_core(
        prices, combined_ind, no_filter, LONG_BIAS,
        LEVAMOUNT, INITIAL_CAPITAL, COMMISSION, SLIPPAGE, MULTIPLIER
    )

    # Create DataFrames
    equity_df = pd.DataFrame({
        'equity': equity_arr,
        'equity_no_filter': equity_no_filter,
        'position': positions,
        'vix': vix_values,
        'vix_filter': vix_filter
    }, index=target_bars.index)

    equity_df['peak'] = equity_df['equity'].cummax()
    equity_df['drawdown'] = (equity_df['peak'] - equity_df['equity']) / equity_df['peak'] * 100

    equity_df['peak_no_filter'] = equity_df['equity_no_filter'].cummax()
    equity_df['drawdown_no_filter'] = (equity_df['peak_no_filter'] - equity_df['equity_no_filter']) / equity_df['peak_no_filter'] * 100

    # Stats comparison
    end_date = equity_df.index[-1].strftime('%Y-%m-%d')
    days_elapsed = (equity_df.index[-1] - equity_df.index[0]).days

    def get_stats(eq_col, dd_col, name):
        final = equity_df[eq_col].iloc[-1]
        ret = (final - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
        cagr = ((final / INITIAL_CAPITAL) ** (365 / days_elapsed) - 1) * 100
        max_dd = equity_df[dd_col].max()
        returns = equity_df[eq_col].pct_change().dropna()
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0
        return {'name': name, 'final': final, 'return': ret, 'cagr': cagr, 'max_dd': max_dd, 'sharpe': sharpe}

    with_filter = get_stats('equity', 'drawdown', f'With VIX Filter (<{VIX_FILTER_THRESHOLD})')
    without_filter = get_stats('equity_no_filter', 'drawdown_no_filter', 'Without VIX Filter')

    print("\n" + "=" * 90)
    print(f"SOD RESULTS - COMPARISON: WITH vs WITHOUT VIX FILTER")
    print("=" * 90)
    print(f"{'Metric':<25} {'Without Filter':>20} {'With Filter':>20} {'Change':>15}")
    print("-" * 80)
    print(f"{'Final Equity':<25} ${without_filter['final']:>18,.0f} ${with_filter['final']:>18,.0f} {(with_filter['final']/without_filter['final']-1)*100:>14.1f}%")
    print(f"{'Total Return':<25} {without_filter['return']:>19.1f}% {with_filter['return']:>19.1f}% {with_filter['return']-without_filter['return']:>14.1f}%")
    print(f"{'CAGR':<25} {without_filter['cagr']:>19.2f}% {with_filter['cagr']:>19.2f}% {with_filter['cagr']-without_filter['cagr']:>14.2f}%")
    print(f"{'Max Drawdown':<25} {without_filter['max_dd']:>19.1f}% {with_filter['max_dd']:>19.1f}% {with_filter['max_dd']-without_filter['max_dd']:>14.1f}%")
    print(f"{'Sharpe Ratio':<25} {without_filter['sharpe']:>19.2f} {with_filter['sharpe']:>19.2f} {with_filter['sharpe']-without_filter['sharpe']:>14.2f}")

    # Period breakdown
    print("\n" + "=" * 90)
    print("PERFORMANCE BY PERIOD (WITH VIX FILTER)")
    print("=" * 90)

    periods = [
        ('Full Period (2010-2025)', '2010-01-01', end_date),
        ('Last 5 Years', '2020-01-01', end_date),
        ('Last 2 Years', '2023-01-01', end_date),
        ('Last 1 Year', '2024-01-01', end_date),
        ('YTD 2025', '2025-01-01', end_date),
    ]

    for period_name, start, end in periods:
        stats = calc_period_stats(equity_df, start, end, period_name)
        if stats:
            print(f"\n{period_name}")
            print(f"  Return: {stats['return_pct']:.1f}%  |  CAGR: {stats['cagr_pct']:.1f}%  |  MaxDD: {stats['max_dd_pct']:.1f}%  |  Sharpe: {stats['sharpe']:.2f}")

    # Save results
    output_dir = os.path.join(script_dir, "results")
    os.makedirs(output_dir, exist_ok=True)
    equity_df.to_csv(os.path.join(output_dir, "sod_vix_filter_equity.csv"))

    # Plot
    print("\n\nGenerating plots...")
    fig, axes = plt.subplots(4, 1, figsize=(14, 14))

    fig.suptitle(f'SOD Strategy ({EXECUTION_TIME}) - VIX Open Filter', fontsize=14, fontweight='bold')

    # 1. Equity comparison
    ax1 = axes[0]
    ax1.plot(equity_df.index, equity_df['equity_no_filter'] / 1e6, linewidth=1.2, color='red', alpha=0.7, label='Without VIX Filter')
    ax1.plot(equity_df.index, equity_df['equity'] / 1e6, linewidth=1.2, color='blue', label='With VIX Filter')
    ax1.set_ylabel('Equity ($M)')
    ax1.set_title('Equity Comparison: With vs Without VIX Filter', fontsize=12)
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.0f}M'))

    # 2. Drawdown comparison
    ax2 = axes[1]
    ax2.fill_between(equity_df.index, equity_df['drawdown_no_filter'], alpha=0.5, color='red', label='Without Filter')
    ax2.fill_between(equity_df.index, equity_df['drawdown'], alpha=0.7, color='blue', label='With Filter')
    ax2.set_ylabel('Drawdown (%)')
    ax2.set_title('Drawdown Comparison', fontsize=12)
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.invert_yaxis()

    # 3. VIX with threshold line
    ax3 = axes[2]
    ax3.plot(equity_df.index, equity_df['vix'], linewidth=0.8, color='purple')
    ax3.axhline(y=VIX_FILTER_THRESHOLD, color='red', linestyle='--', linewidth=2, label=f'Filter Threshold ({VIX_FILTER_THRESHOLD})')
    ax3.fill_between(equity_df.index, VIX_FILTER_THRESHOLD, equity_df['vix'],
                     where=(equity_df['vix'] >= VIX_FILTER_THRESHOLD), alpha=0.3, color='red', label='No Trading Zone')
    ax3.set_ylabel('VIX Open')
    ax3.set_title('VIX Open Level (Red = No Trading)', fontsize=12)
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # 4. Position over time
    ax4 = axes[3]
    ax4.fill_between(equity_df.index, equity_df['position'], alpha=0.7, color='green')
    ax4.set_ylabel('Position (Contracts)')
    ax4.set_xlabel('Date')
    ax4.set_title('Position Size Over Time', fontsize=12)
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    plot_path = os.path.join(output_dir, "sod_vix_filter_chart.png")
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    print(f"Chart saved: {plot_path}")

    plt.close()

    return equity_df, with_filter, without_filter


if __name__ == "__main__":
    equity_df, with_filter, without_filter = main()
