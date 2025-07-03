import logging
import os
import pandas as pd

class Logger:
    def __init__(self, log_folder='Logging', error_log_file='errors.log', info_log_file='info.log', exec_log_file='execution.log', indicators_log_file='indicators.log', symbols=None):
        self.log_folder = log_folder
        self.error_log_file = error_log_file
        self.info_log_file = info_log_file
        self.exec_log_file = exec_log_file
        self.indicators_log_file = indicators_log_file
        self.symbols = symbols if symbols else ['ES']
        
        # Create loggers for error, info, execution, and indicators logs
        self.error_logger = self._setup_logger('error_logger', self.error_log_file, logging.ERROR)
        self.info_logger = self._setup_logger('info_logger', self.info_log_file, logging.INFO)
        self.exec_logger = self._setup_logger('exec_logger', self.exec_log_file, logging.INFO)
        self.indicators_logger = self._setup_logger('indicators_logger', self.indicators_log_file, logging.INFO, custom_formatter=True)
        
        # Create loggers for each symbol
        self.symbol_loggers = {}
        for symbol in self.symbols:
            self.symbol_loggers[symbol] = self._setup_logger(f'{symbol}_logger', f'{symbol}.log', logging.INFO, custom_formatter=True)

    def _setup_logger(self, logger_name, log_file, level, custom_formatter=False):
        if not os.path.exists(self.log_folder):
            os.makedirs(self.log_folder)
        
        log_path = os.path.join(self.log_folder, log_file)
        
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        
        handler = logging.FileHandler(log_path)
        handler.setLevel(level)
        
        if custom_formatter:
            formatter = logging.Formatter('%(asctime)s\n%(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        else:
            formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        
        handler.setFormatter(formatter)
        
        if not logger.handlers:  # Avoid adding multiple handlers to the same logger
            logger.addHandler(handler)
        
        return logger

    def log_error(self, message):
        self.error_logger.error(message)
    
    def log_info(self, message):
        self.info_logger.info(message)
    
    def log_execution(self, message):
        self.exec_logger.info(message)
    
    def log_indicators(self, message):
        self.indicators_logger.info(message)
    
    def log_symbol(self, symbol, message):
        if symbol in self.symbol_loggers:
            self.symbol_loggers[symbol].info(message)
        else:
            raise ValueError(f"No logger found for symbol: {symbol}")

    def log_symbol_dataframe(self, symbol, df):
        if symbol in self.symbols:
            csv_path = os.path.join(self.log_folder, f'{symbol}.csv')
            if not os.path.isfile(csv_path):
                df.to_csv(csv_path, mode='w', header=True, index=True)
            else:
                df.to_csv(csv_path, mode='a', header=False, index=True)
        else:
            raise ValueError(f"No CSV logger found for symbol: {symbol}")