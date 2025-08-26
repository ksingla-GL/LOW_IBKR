import time
import threading
from datetime import datetime
from ib_insync import *
from Logger import Logger


class IBConfig:
    def __init__(self, host="127.0.0.1", port=7497, clientId=0, logging: Logger = None):
        self.host = host
        self.port = port
        self.clientId = clientId
        self.ib = IB()
        self.ib.disconnectedEvent += self.on_disconnected
        self.log = logging if logging is not None else Logger()
        self.reconnection_occurred = False
        self._reconnecting = False

    def open_connection(self):
        try:
            self.ib.connect(self.host, self.port, self.clientId)
            self.log.log_info(f"Connected to IB at {self.host}:{self.port} with clientId {self.clientId}")
            return True
        except Exception as e:
            self.log.log_error(f"An unexpected error occurred: {e}")
            return False

    def close_connection(self):
        try:
            self.ib.disconnect()
            self.log.log_info("Disconnected from IB")
        except Exception as e:
            self.log.log_error(f"An error occurred while disconnecting: {e}")

    def on_disconnected(self):
        """Non-blocking disconnection handler with improved reliability"""
        if hasattr(self, '_reconnecting') and self._reconnecting:
            # Already reconnecting, don't start another thread
            return
            
        self.log.log_error(f"TWS disconnected. Starting reconnection process...")
        self._reconnecting = True
        
        # Use threading to handle reconnection without blocking
        thread = threading.Thread(target=self._reconnect)
        thread.daemon = True
        thread.start()

    def _reconnect(self):
        """Synchronous reconnection logic with improved error handling"""
        reconnect_attempts = 0
        max_attempts = 20  # Reduced from 100 to prevent endless loops
        
        try:
            while reconnect_attempts < max_attempts:
                reconnect_attempts += 1
                
                # Check if we're already connected (might have been reconnected elsewhere)
                if self.ib.isConnected():
                    self.log.log_info("Connection already established, stopping reconnection")
                    self._reconnecting = False
                    self.reconnection_occurred = True
                    return
                
                try:
                    # Progressive backoff: 5, 10, 15, 20, 30, 30... seconds
                    wait_time = min(5 * reconnect_attempts, 30)
                    self.log.log_info(f"Reconnection attempt #{reconnect_attempts} in {wait_time}s")
                    time.sleep(wait_time)
                    
                    # Ensure we're fully disconnected before attempting to reconnect
                    try:
                        if self.ib.isConnected():
                            self.ib.disconnect()
                        time.sleep(1)  # Brief pause to ensure clean disconnect
                    except:
                        pass  # Ignore disconnect errors
                    
                    # Try to reconnect with original parameters
                    self.ib.connect(self.host, self.port, self.clientId)
                    
                    # Verify connection is actually established and stable
                    if self.ib.isConnected():
                        # Wait a moment to ensure the connection is stable
                        time.sleep(2)
                        if self.ib.isConnected():
                            self.log.log_info(f"Successfully reconnected to TWS after {reconnect_attempts} attempts")
                            self._reconnecting = False
                            self.reconnection_occurred = True
                            return
                        
                except Exception as e:
                    self.log.log_error(f"Reconnection attempt #{reconnect_attempts} failed: {e}")
                    # Continue to next attempt
                    
        except Exception as e:
            self.log.log_error(f"Critical error in reconnection process: {e}")
        finally:
            self._reconnecting = False
            
        self.log.log_error(f"Failed to reconnect after {max_attempts} attempts - giving up")

    def check_and_reset_reconnection(self):
        """Check if reconnection occurred and reset the flag"""
        if hasattr(self, 'reconnection_occurred') and self.reconnection_occurred:
            self.reconnection_occurred = False
            return True
        return False
