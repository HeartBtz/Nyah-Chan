#!/usr/bin/env python3
"""
Script de lancement du bot Nyah-Chan (compatible layout src)
"""
import os
import sys

ROOT = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ROOT, 'src'))

from bot.main import main

if __name__ == "__main__":
    main()
