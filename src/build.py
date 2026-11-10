#!/usr/bin/env python3
"""Rebuild the model + charts from the cached data (no network).

Usage: python3 src/build.py
Runs src/model.py then src/charts.py. Re-fetch with src/fetch.py first.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script):
    print(f"=== {script} ===")
    r = subprocess.run([sys.executable, str(HERE / script)], check=False)
    if r.returncode != 0:
        sys.exit(r.returncode)


if __name__ == "__main__":
    run("model.py")
    run("charts.py")
    print("build OK: data/processed/*.json + dashboard/assets/*.png")
