import logging
import asyncio
import time
from datetime import datetime, timedelta
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

def watchdog_callback(config, logger: Logger, ib: IBConfig):
    """Watchdog logic as a callback function"""
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
    
    # Don't reschedule to avoid recursive issues
    # The main watchdog logic will be handled by the initial schedule

def main():
    config = load_config(CONFIG_FILE)
    logger = Logger()
    logger.log_info("Application started")
    
    ib = IBConfig(port=7496, logging=logger)
    
    # Retry initial connection with backoff
    max_attempts = 24  # 24 attempts * 5 seconds = 2 minutes
    attempt = 0
    
    while attempt < max_attempts:
        attempt += 1
        if ib.open_connection():
            logger.log_info("Successfully connected to TWS/IB Gateway")
            break
        else:
            if attempt < max_attempts:
                logger.log_info(f"Connection attempt {attempt}/{max_attempts} failed. Retrying in 5 seconds...")
                time.sleep(5)
            else:
                logger.log_error(f"Failed to connect after {max_attempts} attempts. Please ensure TWS/IB Gateway is running on port 7496.")
                return
    
    # Simple delay for connection stability
    time.sleep(2)
    
    read_trading_parameters(config, ib.ib, ib, logger)
    
    # Simplified approach - schedule periodic watchdog checks without recursion
    def simple_watchdog():
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
    
    # Schedule watchdog to run once after 10 seconds
    start_time = datetime.now() + timedelta(seconds=10)
    ib.ib.schedule(start_time, simple_watchdog)
    
    try:
        ib.ib.run()
    except Exception as e:
        logger.log_error(f"Main loop error: {e}")

if __name__ == "__main__":
    main()
