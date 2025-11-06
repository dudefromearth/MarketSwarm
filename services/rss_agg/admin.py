#!/usr/bin/env python3
import sys, os

# ensure rss_agg package visibility
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from admin.cli import main

if __name__ == "__main__":
    main()