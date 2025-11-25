# # MarketSwarm Mac Setup Guide

This guide walks through setting up a Mac for full MarketSwarm development and operation.
It assumes:
* macOS on Apple Silicon (M1–M4 recommended)
* The MarketSwarm repo lives at: ~/MarketSwarm
* You want a clean, reproducible environment

⠀
⸻

### 1. Install Homebrew
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
Validate:
```bash
brew --version
```

⸻

### 2. Configure Your Shell (zsh)

macOS uses **zsh** by default.
Make sure Homebrew is available in all terminal sessions.

### Add Homebrew environment to zsh

Add this to **both** ~/.zprofile and ~/.zshrc:
```zsh
eval "$(/opt/homebrew/bin/brew shellenv)"
```
One-liner to apply immediately:
```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile && \
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc && \
source ~/.zprofile && source ~/.zshrc
```
**Make zsh your default shell**
```bash
chsh -s /bin/zsh
```
Restart Terminal.

⸻

### 3. Install Homebrew Packages for MarketSwarm

On your original MarketSwarm machine, export the lists:
```bash
brew list --formula > brew-packages.txt
brew list --cask > brew-apps.txt
```
Copy the files to your new Mac, then install:

### Install CLI tools
```bash
xargs -n 1 brew install < brew-packages.txt
```
**Install GUI apps**
```bash
xargs -n 1 brew install --cask < brew-apps.txt
```
Homebrew will skip anything already installed.

⸻

### 4. Python Environment Setup

Inside the repo root (~/MarketSwarm):
```bash
cd ~/MarketSwarm
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```
If service-specific requirements.txt files exist, install those too.

⸻

### 5. Start the MarketSwarm Backbone (Redis Busses)

MarketSwarm uses a multi-Redis bus architecture.

Start the buses:
```bash
./scripts/ms-busses.sh start
```
Stop:
```bash
./scripts/ms-busses.sh stop
```
Verify
```bash
./scripts/ms-busses.sh status
redis-cli -p 6380 PONG
redis-cli -p 6381 PONG
redis-cli -p 6382 PONG
```

⸻

### 6. Install the Truth Layer

Truth seeds core structured knowledge into Redis + system stores.

Load it:
```bash
./scripts/ms-truth.sh load
```
Reset if needed:
```bash
./scripts/ms-truth.sh reset
```

⸻

**7. Verify Full MarketSwarm Environment**

Health check (if available):
```bash
./scripts/ms-health.sh
```

