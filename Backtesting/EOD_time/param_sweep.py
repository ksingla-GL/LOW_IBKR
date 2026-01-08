"""
EOD (15:00 CT) - Static Parameter Sweep
No VIX regime switching - tests all parameter combinations
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from datetime import time
from itertools import product
import os

# =============================================================================
# CONFIGURATION - EOD (15:00 CT)
# =============================================================================

LONG_BIAS_VALUES = [0, 1, 2, 3, 4, 5]

OFFSET_DAYS_COMBOS = []
for d in range(4, 11):
    OFFSET_DAYS_COMBOS.append((3, d))
for d in range(5, 11):
    OFFSET_DAYS_COMBOS.append((4, d))
for d in range(6, 11):
    OFFSET_DAYS_COMBOS.append((5, d))

LEVAMOUNT = 15
TARGET_TIME = time(14, 45)  # 14:45 bar for 15:00 execution
EXECUTION_TIME = "15:00 CT"
DRAWDOWN_LIMIT = 100
INITIAL_CAPITAL = 1_500_000
COMMISSION = 2.50
SLIPPAGE = 0.25
MULTIPLIER = 50
START_DATE = "2010-01-01"


def get_script_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return r"C:\Users\kshit\Desktop\Upwork\LOW_IBKR\Backtesting\EOD_time"


def get_data_dir():
    return os.path.dirname(get_script_dir())


@dataclass
class Config:
    levamount: float
    days: int
    offset: int
    long_bias: float
    initial_capital: float
    commission: float
    slippage: float
    multiplier: float


def run_backtest(config: Config, target_bars: pd.DataFrame) -> dict:
    cash = config.initial_capital
    position = 0
    entry_price = 0.0
    max_equity = config.initial_capital

    trade_pnls = []
    equity_history = []
    min_bars = config.days + 1

    for i in range(min_bars, len(target_bars)):
        bar = target_bars.iloc[i]
        price = bar["close"]

        lookback = target_bars.iloc[i - config.days : i - (config.offset - 1)]
        indicator = lookback["change"].mean()

        raw_lev = indicator + config.long_bias
        net_lev = np.clip(raw_lev, -config.levamount, config.levamount)

        unrealized = position * (price - entry_price) * config.multiplier
        equity = cash + unrealized

        target_value = net_lev * equity
        contract_value = price * config.multiplier
        target_qty = int(target_value // contract_value)
        trade_qty = target_qty - position

        if trade_qty != 0:
            action_sign = 1 if trade_qty > 0 else -1
            abs_qty = abs(trade_qty)
            fill_price = price + (config.slippage * action_sign)
            commission = abs_qty * config.commission

            pnl = 0.0
            old_pos = position
            new_pos = old_pos + trade_qty

            if old_pos == 0:
                entry_price = fill_price
            elif np.sign(new_pos) == np.sign(old_pos):
                if abs(new_pos) > abs(old_pos):
                    total_cost = (abs(old_pos) * entry_price) + (abs_qty * fill_price)
                    entry_price = total_cost / abs(new_pos)
                else:
                    pnl = abs_qty * (fill_price - entry_price) * config.multiplier
                    if old_pos < 0:
                        pnl = -pnl
            elif new_pos == 0:
                pnl = abs(old_pos) * (fill_price - entry_price) * config.multiplier
                if old_pos < 0:
                    pnl = -pnl
                entry_price = 0.0
            else:
                close_qty = abs(old_pos)
                pnl = close_qty * (fill_price - entry_price) * config.multiplier
                if old_pos < 0:
                    pnl = -pnl
                entry_price = fill_price

            position = new_pos
            cash += pnl - commission
            trade_pnls.append(pnl - commission)

        unrealized = position * (price - entry_price) * config.multiplier
        equity = cash + unrealized
        max_equity = max(max_equity, equity)
        equity_history.append(equity)

    final_price = target_bars.iloc[-1]["close"]
    unrealized = position * (final_price - entry_price) * config.multiplier
    final_equity = cash + unrealized

    equity_arr = np.array(equity_history)
    running_max = np.maximum.accumulate(equity_arr)
    drawdowns = (running_max - equity_arr) / running_max * 100
    max_dd = np.max(drawdowns) if len(drawdowns) > 0 else 0

    if len(equity_history) > 1:
        equity_series = pd.Series(equity_history)
        daily_returns = equity_series.pct_change().dropna()
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() > 0 else 0
    else:
        sharpe = 0

    days_elapsed = (target_bars.index[-1] - target_bars.index[0]).days
    total_return = (final_equity - config.initial_capital) / config.initial_capital * 100
    cagr = ((final_equity / config.initial_capital) ** (365 / days_elapsed) - 1) * 100 if days_elapsed > 0 and final_equity > 0 else 0

    winners = [p for p in trade_pnls if p > 0]
    losers = [p for p in trade_pnls if p < 0]
    win_rate = len(winners) / len(trade_pnls) * 100 if trade_pnls else 0
    profit_factor = sum(winners) / abs(sum(losers)) if losers and sum(losers) != 0 else float('inf')

    return {
        "long_bias": config.long_bias,
        "days": config.days,
        "offset": config.offset,
        "final_equity": final_equity,
        "total_return_pct": total_return,
        "cagr_pct": cagr,
        "max_dd_pct": max_dd,
        "sharpe_ratio": sharpe,
        "total_trades": len(trade_pnls),
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor
    }


def main():
    script_dir = get_script_dir()
    data_dir = get_data_dir()

    print("=" * 70)
    print(f"EOD STATIC PARAMETER SWEEP ({EXECUTION_TIME})")
    print(f"Bar time: {TARGET_TIME}")
    print("=" * 70)

    data_path = os.path.join(data_dir, "ES_15min.csv")
    print(f"Loading: {data_path}")

    df = pd.read_csv(data_path)
    df["date"] = pd.to_datetime(df["date"].str.replace(r'[+-]\d{2}:\d{2}$', '', regex=True))
    df.set_index("date", inplace=True)
    df = df[df.index >= START_DATE]

    target_bars = df[df.index.time == TARGET_TIME].copy()
    target_bars["change"] = target_bars["close"] - target_bars["open"]

    print(f"Data range: {df.index[0].date()} to {df.index[-1].date()}")
    print(f"Target time bars: {len(target_bars)}")

    all_combos = list(product(LONG_BIAS_VALUES, OFFSET_DAYS_COMBOS))
    total = len(all_combos)
    print(f"\nTesting {total} parameter combinations...")

    results = []
    for i, (long_bias, (offset, days)) in enumerate(all_combos):
        config = Config(
            levamount=LEVAMOUNT, days=days, offset=offset, long_bias=long_bias,
            initial_capital=INITIAL_CAPITAL, commission=COMMISSION,
            slippage=SLIPPAGE, multiplier=MULTIPLIER
        )
        result = run_backtest(config, target_bars)
        results.append(result)

        if (i + 1) % 20 == 0 or (i + 1) == total:
            print(f"Progress: {i+1}/{total} ({(i+1)/total*100:.0f}%)")

    results_df = pd.DataFrame(results).sort_values("cagr_pct", ascending=False)

    output_dir = os.path.join(script_dir, "results")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "param_sweep_results.csv")
    results_df.to_csv(output_path, index=False)
    print(f"\nResults saved to: {output_path}")

    print("\n" + "=" * 80)
    print("TOP 10 PARAMETER COMBINATIONS (by CAGR)")
    print("=" * 80)

    for idx, (_, row) in enumerate(results_df.head(10).iterrows()):
        print(f"\n#{idx+1}: LongBias={row['long_bias']}, Days={row['days']}, Offset={row['offset']}")
        print(f"    CAGR: {row['cagr_pct']:.2f}%  |  MaxDD: {row['max_dd_pct']:.1f}%  |  Sharpe: {row['sharpe_ratio']:.2f}")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total combinations tested: {len(results_df)}")
    print(f"Profitable (CAGR > 0): {len(results_df[results_df['cagr_pct'] > 0])}")
    print(f"Best CAGR: {results_df['cagr_pct'].max():.2f}%")
    print(f"Median CAGR: {results_df['cagr_pct'].median():.2f}%")


if __name__ == "__main__":
    main()
