import logging
import threading
import asyncio
import time
from typing import Dict
from ib_insync import *
from IBConfig import IBConfig
from ticker import *
from Logger import Logger

logging.getLogger().addHandler(logging.NullHandler())

# Configuration file path
CONFIG_FILE = 'config.txt'

# Load variables from config
def load_config(file_path):
    config = {"Symbol":"ES"}
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()
            for line in lines:
                key, value = line.strip().split('=')
                config[key.strip()] = float(value) if value.strip().replace('.', '').isdigit() else value.strip()
    except Exception as e:
        print(f"Error loading config: {e}")
    return config

strategies: Dict[str, Ticker] = {}

def read_trading_parameters(config,ib:IB,ibconfig,logger):
    strategies["ES"]=Ticker(**config, ib=ib, ibconfig=ibconfig, logging=logger)



def trading_parameter_recreation(config,ib:IB,ibconfig,logger,Symb):
    if Symb=="ES":
        strategies["ES"]=Ticker(**config, ib=ib, ibconfig=ibconfig, logging=logger)
                

def run_watchdog(config, logger: Logger, ib: IBConfig):
    time.sleep(10)  # Initial delay before starting watchdog
    
    while True:
        try:
            # Check if reconnection occurred and restart all symbols if needed
            if ib.check_and_reset_reconnection():
                logger.log_info("Reconnection detected, restarting all symbols to restore market data")
                symbols_list = list(strategies.keys())
                for symbol in symbols_list:
                    trading_parameter_recreation(config=config, ib=ib.ib, ibconfig=ib, logger=logger, Symb=symbol)
            
            symbols_list = list(strategies.keys())
            for i in symbols_list:
                tmp_symbol = strategies[i].watch_dog()
                if tmp_symbol:
                    trading_parameter_recreation(config=config, ib=ib.ib, ibconfig=ib, logger=logger, Symb=tmp_symbol)
        except Exception as e:
            logger.log_error(f"Watchdog Exception occurred: {e}")
        
        time.sleep(60)  # Simple sleep, no asyncio

def main():
    config = load_config(CONFIG_FILE)
    logger = Logger()
    logger.log_info("Application started")
    
    ib = IBConfig(port=7496, logging=logger)
    if not ib.open_connection():
        logger.log_error("Failed to establish initial connection. Exiting.")
        return
    
    # Simple delay for connection stability
    time.sleep(2)
    
    read_trading_parameters(config, ib.ib, ib, logger)
    
    # Fix the watchdog thread - no lambda
    watchdog_thread = threading.Thread(target=run_watchdog, args=(config, logger, ib))
    watchdog_thread.daemon = True
    watchdog_thread.start()
    
    try:
        ib.ib.run()
    except Exception as e:
        logger.log_error(f"Main loop error: {e}")
    

if __name__ == "__main__":
    main()
