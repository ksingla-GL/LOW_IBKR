import asyncio
import time
from ib_async import *
from Logger import Logger
import nest_asyncio

nest_asyncio.apply()


class IBConfig:
    def __init__(self, host="127.0.0.1", port=7497, clientId=0, logging: Logger = None):
        self.host = host
        self.port = port
        self.clientId = clientId
        self.ib = IB()
        self.ib.disconnectedEvent += self.on_disconnected
        self.log = logging if logging is not None else Logger()

    def open_connection(self):
        try:
            self.ib.connect(self.host, self.port, self.clientId)
            self.log.log_info(f"Connected to IB at {self.host}:{self.port} with clientId {self.clientId}")
        except Exception as e:
            self.log.log_error(f"An unexpected error occurred: {e}")
            exit()

    def close_connection(self):
        try:
            self.ib.disconnect()
            self.log.log_info("Disconnected from IB")
        except Exception as e:
            self.log.log_error(f"An error occurred while disconnecting: {e}")

    def on_disconnected(self):
        self.log.log_error(f"TWS disconnected at {datetime.now()}. Starting reconnection...")
        reconnect_attempts = 0
        max_attempts = 100  # Retry for ~16 minutes
        
        while reconnect_attempts < max_attempts:
            reconnect_attempts += 1
            try:
                # Wait before attempting reconnection
                time.sleep(10)
                
                # Try to reconnect with original parameters
                self.log.log_info(f"Reconnection attempt #{reconnect_attempts}")
                self.ib.connect(self.host, self.port, self.clientId)
                
                # Verify connection is actually established
                if self.ib.isConnected():
                    self.log.log_info(f"Successfully reconnected to TWS after {reconnect_attempts} attempts")
                    
                    # Set a flag to indicate reconnection happened
                    self.reconnection_occurred = True
                    return
                    
            except Exception as e:
                self.log.log_error(f"Reconnection attempt #{reconnect_attempts} failed: {e}")
                
        self.log.log_error(f"Failed to reconnect after {max_attempts} attempts")
