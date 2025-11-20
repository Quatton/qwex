#!/usr/bin/env python3
"""
Sample Python script for testing qwex Docker runner.

This script demonstrates that Python code runs successfully
in a Docker container managed by qwex.
"""

import sys
import platform
from datetime import datetime


def main():
    print("=" * 60)
    print("🐍 Python Script Running in Docker via qwex")
    print("=" * 60)

    print(f"\n📅 Timestamp: {datetime.now().isoformat()}")
    print(f"🐍 Python Version: {sys.version}")
    print(f"💻 Platform: {platform.platform()}")
    print(f"🏗️  Architecture: {platform.machine()}")

    print("\n✅ Script executed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
