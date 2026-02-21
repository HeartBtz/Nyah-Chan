#!/usr/bin/env python3
"""
Script de lancement du bot Nyah-Chan (sans interface web)
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

ROOT = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ROOT, 'src'))

from bot.main import main  # noqa: E402

if __name__ == "__main__":
    main()
