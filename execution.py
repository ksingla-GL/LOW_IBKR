from ib_async import *
from numpy import isnan
from Logger import Logger

class ExecuteSignals():
    def __init__(self, ib:IB, logger:Logger):
        self.ib = ib
        self.logger = logger
    
    def create_contract(self, symbol, exchange):
        contract = ContFuture(symbol=symbol, exchange=exchange, currency="USD")
        self.ib.qualifyContracts(contract)
        return contract

    def create_limit_order(self, action, quantity, limit_price, order_type=""):
        order = LimitOrder(action, quantity, limit_price, orderRef=order_type)
        return order
    
    def place_market_order(self, contract, action, quantity):
        order = MarketOrder(action, quantity)
        trade = self.ib.placeOrder(contract, order)
        return trade
    
    def place_stop_order(self, contract, action, stop_price, quantity):
        order = StopOrder(action, quantity, stop_price)
        trade = self.ib.placeOrder(contract, order)
        return trade

    def cancel_open_orders(self, symbol):
        open_orders = self.ib.openTrades()
        for order in open_orders:
            if order.contract.symbol == symbol:
                self.ib.cancelOrder(order.order)
                self.logger.log_execution(f"Cancelled order: {order}")

    def has_open_order(self, symbol):
        open_orders = self.ib.openTrades()
        for order in open_orders:
            if order.contract.symbol == symbol:
                return True
        return False
    
    def get_position(self, symbol):
        positions = self.ib.positions()
        for position in positions:
            if position.contract.symbol == symbol:
                return position
        return None
        
    def create_market_order(self, action, symbol, exchange, quantity, order_type=""):
        order = MarketOrder(action, quantity, orderRef=order_type)
        return order
    
    def place_order(self, contract, order, Symbol):
        trade = self.ib.placeOrder(contract, order)
        order_status = trade.orderStatus.status
        order_action = order.action
        order_quantity = order.totalQuantity
        self.ib.sleep(0.1)
        self.logger.log_execution(f"Order placed successfully: Action={order_action}, Quantity={order_quantity}, Status={order_status}")
        self.logger.log_symbol(Symbol,f"Order placed successfully: Action={order_action}, Quantity={order_quantity}, Status={order_status}")
        self.logger.log_symbol(Symbol,trade)
        return trade
    
    def has_sufficient_funds(self, required_amount):
        available_funds = self.get_available_funds()
        return available_funds >= required_amount
    

    def get_available_funds(self):
        account_summary = self.ib.accountSummary()
        for item in account_summary:
            if item.tag == 'AvailableFunds':
                return float(item.value)
        return 0.0
    
    def get_net_liquidation(self):
        account_summary = self.ib.accountSummary()
        for item in account_summary:
            if item.tag == 'NetLiquidation':
                return float(item.value)
        return 0.0

    def get_market_price(self, contract):
        tickers = self.ib.reqTickers(contract)
        if isnan(tickers[0].marketPrice()):
            self.logger.log_execution(f"Couldn't find market price for this contract : {contract}")
        return tickers[0].marketPrice()
    
    def calculate_ticks(self, stop_loss, tick_value):
        return stop_loss / tick_value
    
    def get_contract_increment(self, contract):
        cd = self.ib.reqContractDetails(contract)[0]
        return self.ib.reqMarketRule(int(cd.marketRuleIds.split(",")[0]))[-1].increment