#!/usr/bin/env python3
from massive import RESTClient
import inspect
import os

# Replace with your actual API key or use environment variable
API_KEY = os.getenv("MASSIVE_API_KEY", "REPLACE_ME")

def list_methods():
    client = RESTClient(API_KEY)
    for name in dir(client):
        if name.startswith("_"):
            continue
        method = getattr(client, name)
        if callable(method):
            sig = inspect.signature(method)
            print(f"{name}{sig}")

if __name__ == "__main__":
    list_methods()