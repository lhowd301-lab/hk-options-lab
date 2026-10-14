"""日志系统"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(name: str = "GammaScalping", config: "Config" = None) -> logging.Logger:
   """配置日志系统"""
   logger = logging.getLogger(name)
   if logger.handlers:
       return logger
   
   if config is None:
       from .config import Config
       config = Config.load()
   
   level = getattr(logging, config.log_level.upper(), logging.INFO)
   logger.setLevel(level)
   
   formatter = logging.Formatter(
       fmt="%(asctime)s.%(msecs)03d | %(levelname)-5s | %(name)s | %(message)s",
       datefmt="%Y-%m-%d %H:%M:%S",
   )
   
   # 控制台输出
   ch = logging.StreamHandler()
   ch.setLevel(level)
   ch.setFormatter(formatter)
   logger.addHandler(ch)
   
   # 文件输出（轮转）
   log_path = Path(config.log_file)
   log_path.parent.mkdir(parents=True, exist_ok=True)
   fh = RotatingFileHandler(
       str(log_path),
       maxBytes=config.log_max_bytes,
       backupCount=config.log_backup_count,
       encoding="utf-8",
   )
   fh.setLevel(level)
   fh.setFormatter(formatter)
   logger.addHandler(fh)
   
   return logger


def get_logger(name: str = "GammaScalping") -> logging.Logger:
   """获取已配置的日志器"""
   logger = logging.getLogger(name)
   if not logger.handlers:
       return setup_logger(name)
   return logger
