# Simple ES Trading System

Single-file ES futures momentum trading system for Interactive Brokers.

## Files
- `trading_system.py` - The complete trading system (~270 lines)
- `config.txt` - Configuration parameters

## Requirements
```
pip install ib_insync pandas nest_asyncio
```

## Usage
1. Start TWS or IB Gateway (port 7496)
2. Run: `python trading_system.py`

## Config Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| LEVAMOUNT | Max leverage (positive/negative cap) | 15 |
| TOTMOUNT | Not used (legacy) | 100 |
| DAYS | Days of historical bars to analyze | 7 |
| OFFSET | Exclude last (OFFSET-1) days from calc | 3 |
| TIME | Execution time (bar close time) | 15:00 |
| DRAWDOWN | Max drawdown % before liquidation | 5 |
| MAXVALUE | Initial high-water mark for drawdown | 100000 |
| LIQ | Liquidation flag (1=stopped trading) | 0 |
| LONG_BIAS | Constant added to indicator | 3 |

## Algorithm

### 1. Indicator Calculation
At target time, calculate average price change from recent bars:
```
selected_bars = bars[-DAYS:-(OFFSET-1)]  # e.g., [-7:-2] = 5 bars
indicator = mean(close - open) for each bar
```

### 2. Leverage Calculation
```
raw_leverage = indicator + LONG_BIAS
net_leverage = clamp(raw_leverage, -LEVAMOUNT, +LEVAMOUNT)
```

### 3. Position Sizing
```
position_value = net_leverage * available_funds
contract_value = ES_price * 50
target_qty = floor(position_value / contract_value)
trade_qty = |target_qty - current_position|
action = BUY if target_qty > current else SELL
```

### 4. Execution
- Executes once per day at target time
- Market orders only
- Auto-liquidates if drawdown > DRAWDOWN%

## Logs
All logs written to `Logging/trading.log`
