#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Kept for compatibility with CLIo 1: ``python main.py`` still starts the engine."""
import sys

from clio import main

if __name__ == "__main__":
    sys.exit(main())
