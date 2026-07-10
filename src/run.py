#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Точка запуска WinPaint (используется системным launcher'ом)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from winpaint.paint import main

if __name__ == "__main__":
    main()
