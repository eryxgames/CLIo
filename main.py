#!/usr/bin/env python3
"""Kept for compatibility with CLIo 1: ``python main.py`` still starts the engine."""
import sys

from clio import main

if __name__ == "__main__":
    sys.exit(main())
