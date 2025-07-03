from ib_async import *
import pandas as pd
from Logger import Logger
from execution import *
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import datetime as dt

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
        ib,
        logging: Logger = None,
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
        self.ib: IB = ib
        self.details = None
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
        


    
    def get_historical_data(self):
        self.log.log_info(f"Processing Symobl {self.Symbol}")
        self.contract = ContFuture(
            symbol=self.Symbol,
            exchange="CME",
            currency="USD",
        )
        self.ib.qualifyContracts(self.contract)
        self.details = self.ib.reqContractDetails(self.contract)
        end_date = dt.datetime.now() - dt.timedelta(days=self.OFFSET)
        try:
            self.bars = self.ib.reqHistoricalData(
                self.contract,
                endDateTime='',
                durationStr=f'{self.DAYS+self.DAYS} D',
                barSizeSetting='15 mins',
                whatToShow='TRADES',
                useRTH=False,
                keepUpToDate=True,
                formatDate=1
            )
            self.historical_data = pd.DataFrame(self.bars)
            self.historical_data["date"] = pd.to_datetime(self.historical_data["date"])
            self.historical_data.set_index("date", inplace=True)
            self.full_historical_data=self.historical_data
            target_time = self.get_target_execution_time(self.TIME)
            self.historical_data = self.historical_data[self.historical_data.index.time == target_time]
            self.log.log_symbol(symbol=self.Symbol,message=self.historical_data)
            self.log.log_indicators(self.full_historical_data.tail(5))
            self.bars.updateEvent += self.bar_handler
        except Exception as e:
            self.log.log_error(f"An unexpected error occurred: {e}")
            
    

    def bar_handler(self, bars, has_new_bar=False):
        target_time = self.get_target_execution_time(self.TIME)
        current_value=self.exec.get_net_liquidation()
        self.MAXVALUE=max(self.MAXVALUE,current_value)
        self.monitor_drawdown(self.MAXVALUE,current_value)
        if not has_new_bar or len(bars) < 2:
            return
        bar = bars[-2]
        self.last_active_bar=pd.DataFrame([bars[-1].dict()])
        self.last_active_bar["date"] = pd.to_datetime(self.last_active_bar["date"])
        self.last_active_bar = self.last_active_bar.set_index("date")
        bar = pd.DataFrame([bar.dict()])
        bar["date"] = pd.to_datetime(bar["date"])
        bar = bar.set_index("date")
        print(f"bar closed {bar.index.time}")
        if self.historical_data.tail(1).index[0] == bar.index[0]:
            self.historical_data.iloc[-1] = bar
            self.full_historical_data.iloc[-1] = bar
            self.log.log_indicators(self.full_historical_data.tail(2))
            self.log.log_symbol(symbol=self.Symbol,message=self.historical_data.tail(-1))
            try:self.execute_orders()
            except Exception as e:
                self.log.log_error(f"Execute Order error occurred: {e}")
        elif self.full_historical_data.tail(1).index[0] != bar.index[0] and bar.index.time != target_time:
            self.full_historical_data = pd.concat([self.full_historical_data, bar], axis=0)
            self.log.log_indicators(self.full_historical_data.tail(2))
        elif self.historical_data.tail(1).index[0] != bar.index[0] and bar.index.time == target_time:
            self.how_many_bars+=1
            self.historical_data = pd.concat([self.historical_data, bar], axis=0)
            self.full_historical_data = pd.concat([self.full_historical_data, bar], axis=0)
            self.log.log_indicators(self.full_historical_data.tail(2))
            self.log.log_symbol(symbol=self.Symbol,message=self.historical_data.tail(-1))
            try:self.execute_orders()
            except Exception as e:
                self.log.log_error(f"Execute Order error occurred: {e}")
            
    
    def is_in_exec_time(self,bar_time):
        target_time = self.get_target_execution_time(self.TIME)
        if target_time==bar_time:return True
        return False
    
    def get_target_execution_time(self,TIME):
        time_obj = dt.datetime.strptime(TIME, "%H:%M").time()
        full_time = dt.datetime.combine(dt.datetime.now().date(), time_obj)
        target_time = full_time - dt.timedelta(minutes=15)
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
        diff_sum=0
        self.historical_data["Change"] = (
            self.historical_data["close"] - self.historical_data["open"]
        )
        strt=int(self.DAYS*-1)
        end=int((self.DAYS-self.OFFSET)*-1)
        for i in range(strt,end,1):
            diff_sum+=float(self.historical_data.iloc[i]["Change"])

        indicator=diff_sum/self.OFFSET
        return indicator

    def execute_orders(self):
        if self.LIQ==1:return
        try:indicator = self.calculate_technical_indicators()
        except Exception as e:
            self.log.log_error(f"Calculate technical data error occurred: {e}"); return
        avilable_funds = self.exec.get_available_funds()
        pos_to_achieve=max(min(indicator + 3,self.LEVAMOUNT), -self.LEVAMOUNT)*avilable_funds
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

        if self.is_in_exec_time(self.historical_data.index[-1].time()) and trade_quantity > 0:
            try:
                self.exec.place_market_order(self.contract, action, trade_quantity)
                self.log.log_execution(f"Order placed successfully: Action={action}, Quantity={trade_quantity}")
                self.log.log_symbol_dataframe(self.Symbol, self.historical_data.iloc[-1:])
            except Exception as e:
                self.log.log_error(f"Execution error occurred: {e}")

    def watch_dog(self):
        if len(self.full_historical_data)==0:
            self.log.log_error(f"Historical data is empty")
            return
        if not self.is_market_open():
            return
        if self.is_during_maintenance():
            self.data_maintinance=True
            return
        if self.data_maintinance==True:
            self.data_maintinance=False
            self.log.log_info(f"*************************************")
            self.log.log_info(f"Restarting symbol after maintinance {self.Symbol} because of market data subscribtion")
            return self.Symbol
        ny_time = datetime.now(ZoneInfo("America/New_York"))
        if len(self.full_historical_data)>1:
            bars_time_frame=((self.full_historical_data.index[-1] - self.full_historical_data.index[-2]).seconds)*2+60
            diff = (ny_time - self.full_historical_data.index[-1]).seconds
            if diff > bars_time_frame:
                self.log.log_info(f"*************************************")
                self.log.log_info(f"Restarting symbol {self.Symbol} because of market data subscribtion")
                # os.execl(sys.executable, sys.executable, *sys.argv)
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
                    start_time = datetime.strptime(start, "%Y%m%d:%H%M").replace(tzinfo=ZoneInfo(tz))
                    end_time = datetime.strptime(end, "%Y%m%d:%H%M").replace(tzinfo=ZoneInfo(tz))
                    now = datetime.now(ZoneInfo(tz))
                    if start_time <= now <= end_time:
                        return True
            return False
        except Exception as e:
            self.log.log_error(f"Session Split Exception occurred: {e}------------{session}")
            if self.is_futures_data_closing():return False
            return True
        

    def is_during_maintenance(self):
        # Define the maintenance start and end times in CT (Central Time)
        maintenance_start = time(23, 0)  # 11:00 PM CT
        maintenance_duration = timedelta(minutes=10)  # Typically 5-10 minutes
        maintenance_end = (datetime.combine(datetime.today(), maintenance_start) + maintenance_duration).time()

        # Get the current time in CT
        current_time = datetime.now(ZoneInfo("America/Chicago")).time()

        # Check if the current time is within the maintenance period
        if maintenance_start <= current_time <= maintenance_end:
            return True
        return False
    
    def is_futures_data_closing(self):
        # Define the futures data closing start and end times in CT (Central Time)
        closing_start = time(16, 0)  # 4:00 PM CT
        closing_end = time(17, 0)    # 5:00 PM CT

        # Get the current time in CT
        current_time = datetime.now(ZoneInfo("America/Chicago")).time()

        # Check if the current time is within the futures data closing period
        return closing_start <= current_time <= closing_end