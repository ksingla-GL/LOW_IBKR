"""
ES Futures Momentum Strategy - Backtest Engine
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, time
import matplotlib.pyplot as plt
import os

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class Config:
    # Strategy params
    levamount: float = 15       # Max leverage
    days: int = 7               # Lookback start
    offset: int = 3             # Lookback end
    time_str: str = "07:30"     # Execution time (Chicago)
    long_bias: float = 3        # Bullish tilt
    drawdown_limit: float = 20  # Max drawdown %

    # Backtest params
    initial_capital: float = 1_500_000
    commission: float = 2.50    # Per contract round-trip
    slippage: float = 0.25      # Points per contract
    multiplier: float = 50      # ES contract multiplier

    @property
    def target_time(self) -> time:
        """Bar time = execution time - 15 min"""
        h, m = map(int, self.time_str.split(":"))
        m -= 15
        if m < 0:
            m += 60
            h -= 1
        return time(h, m)


# =============================================================================
# BACKTEST ENGINE
# =============================================================================

@dataclass
class Trade:
    date: datetime
    action: str
    qty: int
    price: float
    value: float
    commission: float
    pnl: float = 0.0


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: list
    metrics: dict


class Backtester:
    def __init__(self, config: Config):
        self.cfg = config
        self.cash = config.initial_capital
        self.position = 0
        self.entry_price = 0.0
        self.max_equity = config.initial_capital
        self.liquidated = False
        self.trades: list[Trade] = []
        self.equity_history: list[dict] = []

    def run(self, data: pd.DataFrame) -> BacktestResult:
        """Run backtest on 15-min bar data"""

        # Filter to target time bars only
        target_bars = data[data.index.time == self.cfg.target_time].copy()
        target_bars["change"] = target_bars["close"] - target_bars["open"]

        print(f"Total bars: {len(data):,}")
        print(f"Target time bars: {len(target_bars)} ({self.cfg.target_time})")
        print(f"Date range: {target_bars.index[0].date()} to {target_bars.index[-1].date()}")
        print("-" * 50)

        # Need enough history for lookback
        min_bars = self.cfg.days + 1

        for i in range(min_bars, len(target_bars)):
            if self.liquidated:
                break

            bar = target_bars.iloc[i]
            price = bar["close"]

            # Calculate indicator from lookback window
            lookback = target_bars.iloc[i - self.cfg.days : i - (self.cfg.offset - 1)]
            indicator = lookback["change"].mean()

            # Position sizing
            raw_lev = indicator + self.cfg.long_bias
            net_lev = np.clip(raw_lev, -self.cfg.levamount, self.cfg.levamount)

            equity = self._calc_equity(price)
            target_value = net_lev * equity
            contract_value = price * self.cfg.multiplier
            target_qty = int(target_value // contract_value)

            trade_qty = target_qty - self.position

            # Execute trade
            if trade_qty != 0:
                self._execute(bar.name, trade_qty, price)

            # Update equity and check drawdown
            equity = self._calc_equity(price)
            self.max_equity = max(self.max_equity, equity)
            drawdown = (self.max_equity - equity) / self.max_equity * 100

            self.equity_history.append({
                "date": bar.name,
                "equity": equity,
                "drawdown": drawdown,
                "position": self.position
            })

            if drawdown > self.cfg.drawdown_limit:
                self._liquidate(bar.name, price)

        return self._build_result()

    def _calc_equity(self, price: float) -> float:
        """Calculate current equity"""
        unrealized = self.position * (price - self.entry_price) * self.cfg.multiplier
        return self.cash + unrealized

    def _execute(self, date: datetime, qty: int, price: float):
        """Execute a trade"""
        action = "BUY" if qty > 0 else "SELL"
        abs_qty = abs(qty)

        # Apply slippage
        fill_price = price + (self.cfg.slippage if qty > 0 else -self.cfg.slippage)

        # Commission
        commission = abs_qty * self.cfg.commission

        # Calculate PnL and update average entry price
        pnl = 0.0
        old_pos = self.position
        new_pos = old_pos + qty

        if old_pos == 0:
            # Opening new position
            self.entry_price = fill_price
        elif np.sign(new_pos) == np.sign(old_pos):
            # Same direction - either adding or reducing
            if abs(new_pos) > abs(old_pos):
                # Adding to position - compute weighted average entry
                total_cost = (abs(old_pos) * self.entry_price) + (abs_qty * fill_price)
                self.entry_price = total_cost / abs(new_pos)
            else:
                # Reducing position (partial close)
                pnl = abs_qty * (fill_price - self.entry_price) * self.cfg.multiplier
                if old_pos < 0:
                    pnl = -pnl  # Short: profit when price drops
        elif new_pos == 0:
            # Closing entire position
            pnl = abs(old_pos) * (fill_price - self.entry_price) * self.cfg.multiplier
            if old_pos < 0:
                pnl = -pnl
            self.entry_price = 0.0
        else:
            # Flipping position (close old + open new)
            close_qty = abs(old_pos)
            pnl = close_qty * (fill_price - self.entry_price) * self.cfg.multiplier
            if old_pos < 0:
                pnl = -pnl
            self.entry_price = fill_price

        self.position = new_pos
        self.cash += pnl - commission

        trade = Trade(
            date=date,
            action=action,
            qty=abs_qty,
            price=fill_price,
            value=abs_qty * fill_price * self.cfg.multiplier,
            commission=commission,
            pnl=pnl - commission
        )
        self.trades.append(trade)

    def _liquidate(self, date: datetime, price: float):
        """Flatten position on drawdown breach"""
        if self.position != 0:
            self._execute(date, -self.position, price)
        self.liquidated = True
        print(f"LIQUIDATED at {date} - Drawdown limit breached")

    def _build_result(self) -> BacktestResult:
        """Build result object with metrics"""
        eq_df = pd.DataFrame(self.equity_history).set_index("date")

        # Calculate metrics
        initial = self.cfg.initial_capital
        final = eq_df["equity"].iloc[-1]
        days = (eq_df.index[-1] - eq_df.index[0]).days

        total_return = (final - initial) / initial * 100
        cagr = ((final / initial) ** (365 / days) - 1) * 100 if days > 0 else 0
        max_dd = eq_df["drawdown"].max()

        # Daily returns for Sharpe
        eq_df["daily_ret"] = eq_df["equity"].pct_change()
        sharpe = eq_df["daily_ret"].mean() / eq_df["daily_ret"].std() * np.sqrt(252) if eq_df["daily_ret"].std() > 0 else 0

        # Trade stats
        trade_pnls = [t.pnl for t in self.trades]
        winners = [p for p in trade_pnls if p > 0]
        losers = [p for p in trade_pnls if p < 0]

        win_rate = len(winners) / len(trade_pnls) * 100 if trade_pnls else 0
        profit_factor = sum(winners) / abs(sum(losers)) if losers else float('inf')
        avg_trade = np.mean(trade_pnls) if trade_pnls else 0

        metrics = {
            "Initial Capital": f"${initial:,.0f}",
            "Final Equity": f"${final:,.0f}",
            "Total Return": f"{total_return:.2f}%",
            "CAGR": f"{cagr:.2f}%",
            "Max Drawdown": f"{max_dd:.2f}%",
            "Sharpe Ratio": f"{sharpe:.2f}",
            "Total Trades": len(self.trades),
            "Win Rate": f"{win_rate:.1f}%",
            "Profit Factor": f"{profit_factor:.2f}",
            "Avg Trade": f"${avg_trade:,.2f}",
            "Liquidated": self.liquidated
        }

        return BacktestResult(eq_df, self.trades, metrics)


# =============================================================================
# OUTPUT & PLOTTING
# =============================================================================

def print_results(result: BacktestResult):
    """Print summary metrics"""
    print("\n" + "=" * 50)
    print("BACKTEST RESULTS")
    print("=" * 50)
    for k, v in result.metrics.items():
        print(f"{k:.<25} {v}")
    print("=" * 50)


def plot_results(result: BacktestResult, save_path: str = None):
    """Plot equity curve and drawdown"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # Equity curve
    ax1.plot(result.equity_curve["equity"], linewidth=1.5)
    ax1.set_ylabel("Equity ($)")
    ax1.set_title("ES Momentum Strategy - Equity Curve")
    ax1.grid(True, alpha=0.3)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))

    # Drawdown
    ax2.fill_between(result.equity_curve.index,
                     result.equity_curve["drawdown"],
                     alpha=0.7, color='red')
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("Date")
    ax2.grid(True, alpha=0.3)
    ax2.invert_yaxis()

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150)
        print(f"Chart saved: {save_path}")

    plt.show()


def save_trades(result: BacktestResult, path: str):
    """Save trade log to CSV"""
    trades_df = pd.DataFrame([{
        "date": t.date,
        "action": t.action,
        "qty": t.qty,
        "price": t.price,
        "value": t.value,
        "commission": t.commission,
        "pnl": t.pnl
    } for t in result.trades])
    trades_df.to_csv(path, index=False)
    print(f"Trade log saved: {path}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    # Load data
    data_path = os.path.join(os.path.dirname(__file__), "ES_15min.csv")
    print(f"Loading: {data_path}")

    df = pd.read_csv(data_path)

    # Parse dates and strip timezone
    df["date"] = pd.to_datetime(df["date"].str.replace(r'[+-]\d{2}:\d{2}$', '', regex=True))
    df.set_index("date", inplace=True)

    # Run backtest
    config = Config()
    bt = Backtester(config)
    result = bt.run(df)

    # Output
    print_results(result)

    # Save results
    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)

    save_trades(result, os.path.join(results_dir, "trades.csv"))
    result.equity_curve.to_csv(os.path.join(results_dir, "equity_curve.csv"))
    print(f"Equity curve saved: {os.path.join(results_dir, 'equity_curve.csv')}")

    plot_results(result, os.path.join(results_dir, "chart.png"))


if __name__ == "__main__":
    main()
