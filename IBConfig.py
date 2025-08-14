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
            self.log.log_info(
                f"Connected to IB at {self.host}:{self.port} with clientId {self.clientId}"
            )
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
        self.log.log_error(f"TWS disconnected. Reconnecting...")
        while True:
            try:
                if self.ib.isConnected():
                    break
                self.ib.connect(clientId=0)
                self.ib.sleep(10)
            except Exception as e:
                asyncio.run(asyncio.sleep(10))
        self.log.log_info("Reconnected to TWS")
