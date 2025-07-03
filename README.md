# LOW_IBKR

This project executes ES futures trades using parameters defined in `config.txt`. The script reads historical 15 minute bars and determines a leverage ratio based on price changes. A configurable **long bias** value can be added to this ratio.

## Configuration
Edit `config.txt` to adjust trading parameters:

```
LEVAMOUNT=15
TOTMOUNT=100
DAYS=7
OFFSET=3
TIME=15:00
DRAWDOWN=5
MAXVALUE=100000
LIQ=0
LONG_BIAS=3
```

`LONG_BIAS` increases the calculated leverage ratio. For example, if the indicator value from recent bars is `2.5` and `LONG_BIAS` is `3`, then the final value becomes `5.5` and orders are sized to reach a leverage ratio of `5.5` on the tradable portion of the account.

## Running
Install the dependencies from `requirements.txt` and run the main script:

```bash
pip install -r requirements.txt
python main.py
```
