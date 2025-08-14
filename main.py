import logging
import threading
import asyncio
from typing import Dict
from ib_async import *
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

def read_trading_parameters(config,ib:IB,logger):
    strategies["ES"]=Ticker(**config, ib=ib, logging=logger)



def trading_parameter_recreation(config,ib:IB,logger,Symb):
    if Symb=="ES":
        strategies["ES"]=Ticker(**config, ib=ib, logging=logger)
                

def run_watchdog(config, logger: Logger, ib: IBConfig):
    consecutive_failures = 0
    
    while True:
        try:
            # Check main connection first
            if not ib.ib.isConnected():
                logger.log_error("Main connection lost - attempting reconnection")
                ib.open_connection()
                
                # If reconnected, restart all strategies
                if ib.ib.isConnected():
                    logger.log_info("Connection restored - restarting all strategies")
                    read_trading_parameters(config, ib.ib, logger)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures > 5:
                        logger.log_error("Multiple reconnection failures - waiting 5 minutes")
                        time.sleep(300)
            
            # Normal watchdog operations
            symbols_list = list(strategies.keys())
            for i in symbols_list:
                tmp_symbol = strategies[i].watch_dog()
                if tmp_symbol:
                    trading_parameter_recreation(config=config, ib=ib.ib, logger=logger, Symb=tmp_symbol)
                    
        except Exception as e:
            logger.log_error(f"Watchdog Exception occurred: {e}")
            consecutive_failures += 1
            
        finally:
            time.sleep(60)  # Use time.sleep instead of asyncio

def main():
    config = load_config(CONFIG_FILE)
    logger=Logger()
    logger.log_info("Application started")
    ib=IBConfig(port=7496, logging=logger)
    ib.open_connection()
    # ib.ib.execDetailsEvent += _exec_details
    read_trading_parameters(config,ib.ib,logger)
    threading.Thread(target=run_watchdog(config,logger,ib)).start()

    try:
        ib.ib.run()
    except:
        pass
    

if __name__ == "__main__":
    main()
