# synthetic_factory.py
#!/usr/bin/env python3
"""
Synthetic Factory — optional abstraction layer for assembling synthetic
content objects from analysis + graphics.

Currently unused, but included to match the intended architecture.
"""

def build_synthetic_article(category, analysis_text, chart_b64):
    """
    Return a synthetic article object. Orchestrator fills metadata.
    """
    return {
        "category": category,
        "analysis": analysis_text,
        "chart": chart_b64,
    }
