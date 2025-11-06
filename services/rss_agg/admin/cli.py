import sys
from .registry import get, all_strategies

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m rss_agg.admin <strategy>")
        print("Available strategies:")
        for name, desc in all_strategies().items():
            print(f"  {name:20} {desc}")
        sys.exit(0)

    name = sys.argv[1]
    args = sys.argv[2:]
    try:
        strategy = get(name)
        strategy.execute(*args)
    except KeyError as e:
        print(str(e))
        sys.exit(1)