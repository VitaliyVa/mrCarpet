import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

class ImportLogger(logging.Logger):
    def __init__(self, name: str = 'ImportLogger', level = 'INFO', base_path: str = None) -> None:
        super().__init__(name, level)
        self.base_path = base_path
        self.add_formatters()

    def handle_path(self, path):
        if not path:
            raise Exception('path needed')
        if isinstance(path, str):
            return Path(path)
        if isinstance(path, os.PathLike):
            return path

    def add_formatters(self) -> None:
        path = self.handle_path(self.base_path)
        file_handler = RotatingFileHandler(path / 'import_log.log', maxBytes=10*1024*1024)
        stream_handler = logging.StreamHandler()

        file_formatter = logging.Formatter('%(asctime)s %(message)s')
        stream_formatter = logging.Formatter('%(message)s')

        file_handler.setFormatter(file_formatter)
        stream_handler.setFormatter(stream_formatter)

        self.handlers.append(file_handler)
        self.handlers.append(stream_handler)