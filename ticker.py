from ib_insync import *
import pandas as pd
from Logger import Logger
from execution import *
import time
import datetime as dt
from datetime import timedelta
from zoneinfo import ZoneInfo
import os

class Ticker:
    def __init__(
        self,
        Symbol,
        LEVAMOUNT,
        TOTMOUNT,
        DAYS,
        OFFSET,
        TIME,
        DRAWDOWN,
        MAXVALUE,
        LIQ,
        LONG_BIAS,
        ib,
        ibconfig=None,
        logging: Logger = None,
        FORCE_TRADE_ONCE=0,
        TRADE_QTY_OVERRIDE=0,
        LAST_EXECUTION_KEY='',
    ) -> None:
        self.Symbol: str = Symbol
        self.LEVAMOUNT: float = float(LEVAMOUNT)
        self.TOTMOUNT: int = int(TOTMOUNT)
        self.DAYS: int = int(DAYS)
        self.OFFSET: int = int(OFFSET)
        self.TIME: str = TIME
        self.DRAWDOWN: float = float(DRAWDOWN)
        self.MAXVALUE: float = float(MAXVALUE)
        self.LIQ:int = int(LIQ)
        self.LONG_BIAS: float = float(LONG_BIAS)
        self.LAST_EXECUTION_KEY: str = str(LAST_EXECUTION_KEY)
        self.ib: IB = ib
        self.ibconfig = ibconfig
        self.details = None
        self.exchange_tz = None  # exchange timezone resolved from contract details
        self.trade_contract = None  # concrete front-month Future used for orders
        self.log = logging if logging is not None else Logger()
        self.historical_data: pd.DataFrame = pd.DataFrame()
        self.full_historical_data: pd.DataFrame = pd.DataFrame()
        self.last_active_bar: pd.DataFrame = pd.DataFrame()
        self.exec=ExecuteSignals(ib,logging)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        self.how_many_bars=0
        self.data_maintinance=False
        self.get_historical_data()
        # Force-trade settings (optional in config)
        try:
            self.FORCE_TRADE_ONCE = int(FORCE_TRADE_ONCE)
        except Exception:
            self.FORCE_TRADE_ONCE = 0
        try:
            self.TRADE_QTY_OVERRIDE = int(TRADE_QTY_OVERRIDE)
        except Exception:
            self.TRADE_QTY_OVERRIDE = 0
        
        # Initialize leverage ratio log file
        self.leverage_log_file = os.path.join("Logging", f"leverage_ratio_log_{self.Symbol}.txt")
        self.init_leverage_log()
        #print(f"Leverage log will be saved to: {os.path.abspath(self.leverage_log_file)}")
        


    def init_leverage_log(self):
        """Initialize the leverage ratio log file with headers"""
        with open(self.leverage_log_file, 'a') as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"Leverage Ratio Log for {self.Symbol} - Started at {dt.datetime.now()}\n")
            f.write("="*80 + "\n")
            f.write("Timestamp | Base Indicator | Long Bias | Raw Leverage | Net Leverage | Net Liquidation | Position to Achieve | Action | Quantity\n")
            f.write("-"*80 + "\n")
    
    
    def log_leverage_ratio(self, indicator, raw_leverage, Net_leverage, net_liquidation, pos_to_achieve, action, quantity):
        """Log the leverage ratio calculation to a notepad file"""
        timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        log_entry = (
            f"{timestamp} | "
            f"{indicator:>14.4f} | "
            f"{self.LONG_BIAS:>9.2f} | "
            f"{raw_leverage:>12.4f} | "
            f"{Net_leverage:>16.4f} | "
            f"{net_liquidation:>15.2f} | "
            f"{pos_to_achieve:>19.2f} | "
            f"{action:>6} | "
            f"{quantity:>8}\n"
        )
        
        # Write to file
        with open(self.leverage_log_file, 'a') as f:
            f.write(log_entry)
        
        # Also log to console for immediate visibility
        self.log.log_info(f"LEVERAGE RATIO: Base={indicator:.4f}, Bias={self.LONG_BIAS}, "
                         f"Raw={raw_leverage:.4f}, Net={Net_leverage:.4f}, "
                         f"NetLiq=${net_liquidation:,.2f}, PosToAchieve=${pos_to_achieve:,.2f}")
    
    
    def get_historical_data(self):
        self.log.log_info(f"Processing Symobl {self.Symbol}")
        self.contract = ContFuture(
            symbol=self.Symbol,
            exchange="CME",
            currency="USD",
        )
        self.ib.qualifyContracts(self.contract)
        self.details = self.ib.reqContractDetails(self.contract)
        if not self.details:
            self.log.log_error("No contract details returned for ContFuture; cannot proceed.")
            return
        # Resolve exchange timezone from details
        try:
            tz_id = self.details[0].timeZoneId
            self.exchange_tz = ZoneInfo(tz_id)
        except Exception:
            # Fallback to Chicago for CME futures
            self.exchange_tz = ZoneInfo("America/Chicago")

        # Resolve a tradable front-month Future contract to place orders on
        try:
            def parse_month(s: str) -> int:
                # Handles YYYYMM or YYYYMMDD formats
                if not s:
                    return 99999999
                try:
                    return int(s[:8]) if len(s) >= 8 else int(s[:6])
                except Exception:
                    return 99999999

            fut_details = [d for d in self.details if getattr(d.contract, 'secType', '') == 'FUT']
            if fut_details:
                # Choose the first upcoming contract by lastTradeDateOrContractMonth
                now_key = int(dt.datetime.now(self.exchange_tz).strftime("%Y%m%d"))
                fut_details.sort(key=lambda d: (
                    parse_month(getattr(d.contract, 'lastTradeDateOrContractMonth', '99999999')) < now_key,
                    parse_month(getattr(d.contract, 'lastTradeDateOrContractMonth', '99999999'))
                ))
                self.trade_contract = fut_details[0].contract
                self.trade_contract.exchange = "CME"
            else:
                # Fallback: try first detail's contract
                try:
                    front = self.details[0].contract
                    front.exchange = "CME"
                    self.trade_contract = front
                except Exception:
                    self.trade_contract = None
            if self.trade_contract is None:
                self.log.log_error("Failed to resolve a tradable front-month Future contract. Orders will fail.")
            else:
                self.log.log_info(
                    f"Using trade contract: {self.trade_contract.symbol} "
                    f"{getattr(self.trade_contract, 'lastTradeDateOrContractMonth', '')} @ {self.trade_contract.exchange}"
                )
        except Exception as e:
            self.log.log_error(f"Error resolving trade contract: {e}")
        end_date = dt.datetime.now() - dt.timedelta(days=self.OFFSET)
        try:
            self.log.log_info(f"Requesting historical data for {self.Symbol} with keepUpToDate=True")
            self.bars = self.ib.reqHistoricalData(
                self.contract,
                endDateTime='',
                durationStr='30 D',
                barSizeSetting='15 mins',
                whatToShow='TRADES',
                useRTH=False,
                keepUpToDate=True,
                formatDate=1
            )
            self.log.log_info(f"Historical data request successful. Got {len(self.bars)} bars")
            
            self.historical_data = pd.DataFrame(self.bars)
            self.historical_data["date"] = pd.to_datetime(self.historical_data["date"])
            self.historical_data.set_index("date", inplace=True)
            self.full_historical_data=self.historical_data
            
            target_time = self.get_target_execution_time(self.TIME)
            self.log.log_info(f"Filtering data for target time: {target_time}")
            
            self.historical_data = self.historical_data[self.historical_data.index.time == target_time]
            self.log.log_info(f"After filtering: {len(self.historical_data)} trading bars, {len(self.full_historical_data)} total bars")
            
            # Log the most recent bars
            if len(self.full_historical_data) > 0:
                last_bar = self.full_historical_data.tail(1).index[0]
                self.log.log_info(f"Most recent bar timestamp: {last_bar}")
            
            self.log.log_symbol(symbol=self.Symbol,message=self.historical_data)
            self.log.log_indicators(self.full_historical_data.tail(5))
            
            # Subscribe to bar updates
            self.log.log_info("Subscribing to bar updates via updateEvent")
            self.bars.updateEvent += self.bar_handler
            self.log.log_info("Bar handler subscription complete")
            
        except Exception as e:
            self.log.log_error(f"Historical data setup error: {e}")
            import traceback
            self.log.log_error(f"Full traceback: {traceback.format_exc()}")
            
    

    def bar_handler(self, bars, has_new_bar=False):
        # Debug logging to understand bar updates
        self.log.log_info(f"BAR HANDLER CALLED: has_new_bar={has_new_bar}, bars_count={len(bars)}")
        
        target_time = self.get_target_execution_time(self.TIME)
        self.log.log_info(f"Target execution time: {target_time}")
        
        current_value=self.exec.get_net_liquidation()
        self.MAXVALUE=max(self.MAXVALUE,current_value)
        self.monitor_drawdown(self.MAXVALUE,current_value)
        
        if not has_new_bar:
            self.log.log_info("No new bar - exiting handler")
            return
        if len(bars) < 2:
            self.log.log_info(f"Not enough bars ({len(bars)}) - exiting handler")
            return
            
        bar = bars[-2]
        self.log.log_info(f"Processing new bar from bars[-2]")
        self.last_active_bar=pd.DataFrame([bars[-1].dict()])
        self.last_active_bar["date"] = pd.to_datetime(self.last_active_bar["date"])
        self.last_active_bar = self.last_active_bar.set_index("date")
        bar = pd.DataFrame([bar.dict()])
        bar["date"] = pd.to_datetime(bar["date"])
        bar = bar.set_index("date")
        
        bar_time = bar.index[0].time()
        self.log.log_info(f"New bar closed at: {bar.index[0]} (time: {bar_time})")
        self.log.log_info(f"Target time check: {bar_time} == {target_time} ? {bar_time == target_time}")
        
        print(f"bar closed {bar.index.time}")
        
        if self.historical_data.tail(1).index[0] == bar.index[0]:
            self.log.log_info("Updating existing bar (same timestamp)")
            self.historical_data.iloc[-1] = bar
            self.full_historical_data.iloc[-1] = bar
            self.log.log_indicators(self.full_historical_data.tail(2))
            self.log.log_symbol(symbol=self.Symbol,message=self.historical_data.tail(-1))
            try:self.execute_orders()
            except Exception as e:
                self.log.log_error(f"Execute Order error occurred: {e}")
        elif self.full_historical_data.tail(1).index[0] != bar.index[0] and bar_time != target_time:
            self.log.log_info(f"Adding new bar to full_historical_data (not target time: {bar_time} != {target_time})")
            self.full_historical_data = pd.concat([self.full_historical_data, bar], axis=0)
            self.log.log_indicators(self.full_historical_data.tail(2))
        elif self.historical_data.tail(1).index[0] != bar.index[0] and bar_time == target_time:
            self.how_many_bars+=1
            self.log.log_info(f"*** TRADING BAR DETECTED *** Time: {bar_time} matches target: {target_time}")
            self.log.log_info(f"Adding bar to both historical_data and full_historical_data")
            self.historical_data = pd.concat([self.historical_data, bar], axis=0)
            self.full_historical_data = pd.concat([self.full_historical_data, bar], axis=0)
            self.log.log_indicators(self.full_historical_data.tail(2))
            self.log.log_symbol(symbol=self.Symbol,message=self.historical_data.tail(-1))
            self.log.log_info("*** EXECUTING ORDERS ***")
            try:self.execute_orders()
            except Exception as e:
                self.log.log_error(f"Execute Order error occurred: {e}")
        else:
            self.log.log_info(f"Bar doesn't match any condition - skipping")
            
    
    def is_in_exec_time(self,bar_time):
        target_time = self.get_target_execution_time(self.TIME)
        if target_time==bar_time:return True
        return False
    
    def get_target_execution_time(self,TIME):
        # Interpret TIME in the instrument's exchange timezone (e.g., CME for ES)
        try:
            tz = self.exchange_tz if self.exchange_tz else ZoneInfo("America/Chicago")
        except Exception:
            tz = ZoneInfo("America/Chicago")
        time_obj = dt.datetime.strptime(TIME, "%H:%M").time()
        full_time = dt.datetime.combine(dt.datetime.now(tz).date(), time_obj)
        target_time = full_time - dt.timedelta(minutes=15)
        if self.exchange_tz:
            self.log.log_info(f"Config TIME={TIME} interpreted in {self.exchange_tz.key}; target start={target_time.time()}")
        else:
            self.log.log_info(f"Config TIME={TIME} interpreted in America/Chicago; target start={target_time.time()}")
        return target_time.time()
    
    def monitor_drawdown(self,account_value, current_value):
        drawdown = (account_value - current_value) / account_value * 100
        if self.LIQ==1:return
        if drawdown > self.DRAWDOWN:
            self.log.log_execution(f"Drawdown exceeded {self.DRAWDOWN}%. Closing all positions.")
            self.LIQ=1
            position = self.exec.get_position(self.Symbol)
            self.update_config()
            if position:
                if position.position > 0:
                    position.contract.exchange = "CME"
                    self.exec.cancel_open_orders(self.Symbol)
                    order = self.exec.create_market_order('SELL', self.Symbol, "CME", position.position)
                    return self.exec.place_order(position.contract, order, self.Symbol)
                elif position.position < 0:
                    position.contract.exchange = "CME"
                    self.exec.cancel_open_orders(self.Symbol)
                    order = self.exec.create_market_order('BUY', self.Symbol, "CME", position.position*-1)
                    return self.exec.place_order(position.contract, order, self.Symbol)
                
    def update_config(self):
        file_path="config.txt"
        with open(file_path, 'r') as file:
            lines = file.readlines()
        for i, line in enumerate(lines):
            if line.startswith("LIQ="):
                lines[i] = "LIQ=1"
        with open(file_path, 'w') as file:
            file.writelines(lines)

    def calculate_technical_indicators(self):
        # Filter for target time bars only
        target_time = self.get_target_execution_time(self.TIME)
        daily_bars = self.full_historical_data[self.full_historical_data.index.time == target_time].copy()
        
        daily_bars["Change"] = daily_bars["close"] - daily_bars["open"]
        
        # Check if today's bar is in the data
        today = dt.datetime.now().date()
        last_bar_date = daily_bars.index[-1].date() if len(daily_bars) > 0 else None
        
        selected_days = daily_bars.iloc[-self.DAYS:-(self.OFFSET-1)]
        """
        if last_bar_date == today:
            # Today's bar is present, exclude it
            self.log.log_info(f"Today's bar found in data, excluding it")
            # -8:-3 to get 7,6,5,4,3 days ago (excluding today at -1)
            selected_days = daily_bars.iloc[-(self.DAYS+1):-(self.OFFSET)]  
        else:
            # Today's bar not present yet
            self.log.log_info(f"Today's bar not in data yet")
            # -7:-2 to get 7,6,5,4,3 days ago (when today isn't there)
            selected_days = daily_bars.iloc[-self.DAYS:-(self.OFFSET-1)]
        """
        # Debug logging
        self.log.log_info(f"Calculating from {len(selected_days)} bars: {selected_days.index.tolist()}")
        self.log.log_info(f"Changes: {selected_days['Change'].values}")
        
        indicator = selected_days["Change"].mean()
        self.log.log_info(f"Final indicator value: {indicator}")
        
        return indicator

    def execute_orders(self):
        if self.LIQ==1:return

        try:indicator = self.calculate_technical_indicators()
        except Exception as e:
            self.log.log_error(f"Calculate technical data error occurred: {e}"); return

        # Check if already executed at this time today to prevent duplicate orders
        today = dt.datetime.now().date()
        execution_key = f"{today}_{self.TIME}"  # e.g., "2025-09-10_9:30"
        if self.LAST_EXECUTION_KEY and self.LAST_EXECUTION_KEY == execution_key:
            self.log.log_info(f"Orders already executed for {execution_key} - skipping duplicate execution")
            return

        # Forced one-shot trade path: avoids blocking IB calls in event-loop callbacks
        if getattr(self, 'FORCE_TRADE_ONCE', 0) == 1:
            try:
                raw_leverage = indicator + self.LONG_BIAS
                action = "BUY" if raw_leverage >= 0 else "SELL"
                qty = int(getattr(self, 'TRADE_QTY_OVERRIDE', 0) or 1)
                if self.trade_contract is None:
                    self.log.log_error("No trade contract resolved; cannot place forced order.")
                    return
                self.exec.place_market_order_nb(self.trade_contract, action, qty)
                self.log.log_execution(f"Forced one-shot order submitted: Action={action}, Quantity={qty}")
                # Mark execution key to prevent duplicate runs today
                self._update_execution_key(execution_key)
                self._reset_force_trade_flag()
            except Exception as e:
                self.log.log_error(f"Forced trade error: {e}")
            return

        # Get net liquidation value
        net_liquidation = self.exec.get_net_liquidation()
        
        # Calculate leverage ratios
        raw_leverage = indicator + self.LONG_BIAS
        Net_leverage = max(min(raw_leverage, self.LEVAMOUNT), -self.LEVAMOUNT)
        
        # Calculate position to achieve
        pos_to_achieve = Net_leverage * self.exec.get_available_funds()
        
        contract_price=self.full_historical_data.iloc[-1]["close"]
        multiplier=50
        contract_value=contract_price*multiplier
        position = self.exec.get_position(self.Symbol)
        if position:current_position=position.position
        else:current_position=0
        quantity=round(pos_to_achieve // contract_value)

        if quantity > current_position:
            action = "BUY"
            trade_quantity = quantity - current_position
        else:
            action = "SELL"
            trade_quantity = current_position - quantity

        # Log leverage ratio information
        self.log_leverage_ratio(
            indicator=indicator,
            raw_leverage=raw_leverage,
            Net_leverage=Net_leverage,
            net_liquidation=net_liquidation,
            pos_to_achieve=pos_to_achieve,
            action=action,
            quantity=trade_quantity
        )

        # Ensure we have a tradable contract resolved
        if self.trade_contract is None:
            self.log.log_error("No trade contract resolved; cannot place order. Check contract details and exchange.")
            return
        if self.is_in_exec_time(self.historical_data.index[-1].time()) and trade_quantity > 0:
            try:
                self.exec.place_market_order_nb(self.trade_contract, action, trade_quantity)
                self.log.log_execution(f"Order placed successfully: Action={action}, Quantity={trade_quantity}")
                self.log.log_symbol_dataframe(self.Symbol, self.historical_data.iloc[-1:])
                # Mark execution key to prevent duplicate runs today
                self._update_execution_key(execution_key)
            except Exception as e:
                self.log.log_error(f"Execution error occurred: {e}")

    def watch_dog(self):
        # First check if we're actually connected
        if not self.ib.isConnected():
            self.log.log_error(f"Connection lost for {self.Symbol}")
            # Don't attempt reconnection here - let IBConfig handle it automatically
            # Just signal that this symbol needs to be restarted when connection is restored
            return self.Symbol
        
        if len(self.full_historical_data) == 0:
            self.log.log_error(f"Historical data is empty")
            return
            
        if not self.is_market_open():
            return
            
        if self.is_during_maintenance():
            self.data_maintinance = True
            return
            
        if self.data_maintinance == True:
            self.data_maintinance = False
            self.log.log_info(f"*************************************")
            self.log.log_info(f"Restarting symbol after maintenance {self.Symbol}")
            return self.Symbol
        
        # Check for stale data
        ny_time = dt.datetime.now(ZoneInfo("America/New_York"))
        if len(self.full_historical_data) > 1:
            bars_time_frame = ((self.full_historical_data.index[-1] - self.full_historical_data.index[-2]).seconds) * 2 + 60
            diff = (ny_time - self.full_historical_data.index[-1]).seconds
            
            # If data is stale OR no bar updates for too long
            if diff > bars_time_frame or diff > 1800:  # 30 minutes max
                self.log.log_info(f"*************************************")
                self.log.log_info(f"Restarting symbol {self.Symbol} - data stale for {diff} seconds")
                return self.Symbol


    def is_market_open(self):
        if not self.ib.isConnected():return False
        tz = self.details[0].timeZoneId
        trading_hours = self.details[0].tradingHours
        session = trading_hours.split(";")
        # if 'CLOSED' in session[0]:return False
        try:
            for sess in session:
                if 'CLOSED' in sess:continue
                if len(sess.split("-"))>1:
                    start, end = sess.split("-")[:2]
                    start_time = dt.datetime.strptime(start, "%Y%m%d:%H%M").replace(tzinfo=ZoneInfo(tz))
                    end_time = dt.datetime.strptime(end, "%Y%m%d:%H%M").replace(tzinfo=ZoneInfo(tz))
                    now = dt.datetime.now(ZoneInfo(tz))
                    if start_time <= now <= end_time:
                        return True
            return False
        except Exception as e:
            self.log.log_error(f"Session Split Exception occurred: {e}------------{session}")
            if self.is_futures_data_closing():return False
            return True
        

    def is_during_maintenance(self):
        # Define the maintenance start and end times in CT (Central Time)
        maintenance_start = dt.time(23, 0)  # 11:00 PM CT
        maintenance_duration = timedelta(minutes=10)  # Typically 5-10 minutes
        maintenance_end = (dt.datetime.combine(dt.datetime.today(), maintenance_start) + maintenance_duration).time()

        # Get the current time in CT
        current_time = dt.datetime.now(ZoneInfo("America/Chicago")).time()

        # Check if the current time is within the maintenance period
        if maintenance_start <= current_time <= maintenance_end:
            return True
        return False
    
    def is_futures_data_closing(self):
        # Define the futures data closing start and end times in CT (Central Time)
        closing_start = dt.time(16, 0)  # 4:00 PM CT
        closing_end = dt.time(17, 0)    # 5:00 PM CT

        # Get the current time in CT
        current_time = dt.datetime.now(ZoneInfo("America/Chicago")).time()

        # Check if the current time is within the futures data closing period
        return closing_start <= current_time <= closing_end

    def _reset_force_trade_flag(self):
        """Set FORCE_TRADE_ONCE=0 in config to avoid repeat."""
        try:
            file_path = "config.txt"
            with open(file_path, 'r') as f:
                lines = f.readlines()
            found = False
            for i, line in enumerate(lines):
                if line.startswith("FORCE_TRADE_ONCE="):
                    lines[i] = "FORCE_TRADE_ONCE=0\n"
                    found = True
                    break
            if not found:
                lines.append("FORCE_TRADE_ONCE=0\n")
            with open(file_path, 'w') as f:
                f.writelines(lines)
            self.FORCE_TRADE_ONCE = 0
        except Exception as e:
            self.log.log_error(f"Failed to reset FORCE_TRADE_ONCE flag: {e}")

    def _update_execution_key(self, execution_key):
        """Update LAST_EXECUTION_KEY in config.txt to prevent duplicate executions."""
        try:
            file_path = "config.txt"
            with open(file_path, 'r') as f:
                lines = f.readlines()
            found = False
            for i, line in enumerate(lines):
                if line.startswith("LAST_EXECUTION_KEY="):
                    lines[i] = f"LAST_EXECUTION_KEY={execution_key}\n"
                    found = True
                    break
            if not found:
                # Ensure the last line has a proper newline before appending
                if lines and not lines[-1].endswith('\n'):
                    lines[-1] = lines[-1] + '\n'
                lines.append(f"LAST_EXECUTION_KEY={execution_key}\n")
            with open(file_path, 'w') as f:
                f.writelines(lines)
            self.LAST_EXECUTION_KEY = execution_key
            self.log.log_info(f"Updated execution key to: {execution_key}")
        except Exception as e:
            self.log.log_error(f"Failed to update execution key: {e}")
