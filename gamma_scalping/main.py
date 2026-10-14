"""Gamma Scalping System - Top-level Entry Point

Run: python main.py

基于富途 OpenAPI (FutuOpenD) 的腾讯 00700.HK 个股期权
Gamma Scalping 自动化交易系统。
"""

import sys
import os

# Ensure the package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gamma_scalping.main import main


if __name__ == "__main__":
    sys.exit(main())
