# graphics/render.py
#!/usr/bin/env python3
"""
render.py — Chart/graphic generator for content_anal
Simple baseline implementation using matplotlib.
Generates a bar chart of article count per category and returns
base64-encoded PNG.
"""

import io
import base64
import matplotlib.pyplot as plt


def generate_chart(category, items=None, schema=None):
    """
    Create a simple bar chart showing the number of items analyzed.
    Returns base64-encoded PNG.
    """
    count = len(items) if items else 0

    fig, ax = plt.subplots(figsize=(3, 2))
    ax.bar([category], [count], color="#4C72B0")
    ax.set_title(f"{category} items")
    ax.set_ylabel("count")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    return base64.b64encode(buf.read()).decode()