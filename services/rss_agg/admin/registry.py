from typing import Dict, Type
from .base import BaseStrategy

_registry: Dict[str, Type[BaseStrategy]] = {}

def register(strategy_class: Type[BaseStrategy]):
    """Decorator to register a strategy in the registry."""
    _registry[strategy_class.name] = strategy_class
    return strategy_class

def get(name: str) -> BaseStrategy:
    if name not in _registry:
        raise KeyError(f"Unknown strategy: {name}")
    return _registry[name]()

def all_strategies():
    return {n: c.description for n, c in _registry.items()}