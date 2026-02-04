# FOTW Trading Methodology

## Intellectual Foundation

This methodology is built on the work of:

- **Benoit Mandelbrot** - Fractal geometry, market memory, fat tails
- **Nassim Taleb** - Black Swans, Antifragility, Convexity, Fooled by Randomness
- **Mark Spitznagel** - Tail-risk hedging, Austrian economics applied to trading
- **Austrian Economic Theory** - Boom-bust cycles, time preference, malinvestment

---

## Core Principles

### What Matters

| Concept | What It Is | Why It Matters |
|---------|------------|----------------|
| **Market Structure** | Topology of volume - nodes, wells, edges | Market memory made visible. Real levels that persist and get respected. |
| **Convexity** | Pricing anomalies - cheaper than neighbors | The edge. Finding trades where you pay less for the same optionality. |
| **Asymmetry** | Risk small, make large (R2R) | The payoff structure. Limited downside, unlimited upside. |
| **Fractals** | Self-similar structure across scales | Mandelbrot's proof that markets have memory. Structure repeats. |
| **Optionality** | Preserving choices, never forced | Sovereignty. Always have exits, never be trapped. |

### What's Voodoo

Most of Technical Analysis:
- Moving averages, RSI, MACD, Stochastics
- Fibonacci retracements, Elliott Wave
- Arbitrary trendlines and support/resistance
- POC, VAH, VAL (Market Profile holdovers)
- Any indicator without a causal mechanism

These are either lagging, arbitrary, or have no causal mechanism connecting them to market behavior. They're the broker narrative - designed to keep retail busy drawing lines while missing actual structure.

---

## The Counter-Intuitive Truth About VIX and Risk

### Low VIX (≤17) = HIGHER RISK for 0-2 DTE Traders

| Factor | Effect | Trader Response |
|--------|--------|-----------------|
| Less premium available | Smaller profit potential | Must be selective |
| Higher Gamma | Price sensitivity amplified | Small moves hurt more |
| Faster decay | Less time to be wrong | Must be opportunistic |
| Compressed ATR | Less intraday movement | Harder to hit OTM flies |

### High VIX (≥23+) = LOWER RISK for 0-2 DTE Traders

| Factor | Effect | Trader Response |
|--------|--------|-----------------|
| More premium available | Larger profit potential | More to work with |
| Lower Gamma | Less price sensitivity | Small moves don't hurt as much |
| Slower decay | Time is on your side | Can be patient |
| Higher ATR | Must go WIDER | Adjust width to regime |

**The Secret:** Maintain consistent R2R ranges across VIX levels. Adjust width, DTE, and management style - but keep R2R consistent.

---

## VIX Regimes

| Regime | VIX | Width | DTE | Risk Profile |
|--------|-----|-------|-----|--------------|
| Zombieland | <17 | 20-30 | 0-1 | Higher risk - fast decay, high gamma |
| Goldilocks 1 | 17-23 | 30-40 | 0-1 | Moderate |
| Goldilocks 2 | 23-32 | 40-50 | 0-2 | Lower risk - more premium |
| Chaos | 32+ | 50-100 | 1-3 | Lowest risk* - slow decay, patience required |

*Lowest gamma/decay risk, but requires wider structures and longer holding periods.

---

## Campaign Framework

Trading strategies are organized into campaigns by timeframe.

### Campaign 1: 0-2 DTE Tactical

| Attribute | Value |
|-----------|-------|
| Strategies | 0DTE Tactical, TimeWarp, Batman, Gamma Scalp |
| Frequency | 3-7 trades/week |
| R2R Target | 9-18 |
| Debit Range | 7-10% of width |
| Focus | VIX regime alignment, session timing |

### Campaign 2: Convex Stack (3-5 DTE)

| Attribute | Value |
|-----------|-------|
| Frequency | 2 trades/week (overlapping allowed) |
| R2R Target | 15-30 |
| Debit Range | 5-7% of width |
| Focus | **CONVEXITY** - finding pricing anomalies |

### Campaign 3: Sigma Drift (5-10 DTE)

| Attribute | Value |
|-----------|-------|
| Frequency | 6/month (4 weekly + 2 floaters) |
| R2R Target | 20-50 |
| Debit Range | 3-5% of width |
| Focus | **CONVEXITY** + macro/structure awareness |
| Floaters | Strategic, timed around macro events |

### Portfolio R2R by Campaign Mix

| Campaign Mix | Avg R2R | Strategy |
|--------------|---------|----------|
| 0DTE Dominant | 10-12 | High frequency, tactical |
| Balanced | 15-20 | Diversified across all campaigns |
| Longer-Dated Dominant | 25-35 | Selective 0DTE, lean into convexity |

**Key Pattern:** As DTE increases:
- R2R expectations increase (9-18 → 15-30 → 20-50)
- Frequency decreases
- Convexity becomes the dominant selection criterion
- Win rate decreases slightly but distribution has fatter right tails

---

## Edge Case Strategies

### TimeWarp (VIX ≤17)

**Trigger:** Low VIX with two converging factors:
1. Accelerated premium decay (0DTE premium evaporates too fast)
2. Compressed intraday movement / overnight gap dominance

**Solution:** Go out 1-2 DTE to capture:
- Slower relative decay (more premium runway)
- Overnight Globex movement

**Width:** 10-20 (narrower)
**Frequency:** Increases as VIX decreases

### Batman (VIX 24+)

**Structure:** Two butterflies - Put fly below spot + Call fly above spot

```
    Put Fly          SPOT          Call Fly
[----50w----]         ↑         [----50w----]
```

**Standard:** Equal widths (e.g., two 50-wide)
**Skewed:** Adjust based on gamma/Volume Profile structure

**Debit Rule:** Combined debit ≤ 10% of combined width
**Width:** 30-50+ (wider usually better)
**Frequency:** Increases as VIX rises from Goldilocks 2 into Chaos

### Gamma Scalp (Late Day 0DTE)

**What:** High-gamma fly exploiting structural setup for quick profit

**Time Window by VIX:**

| VIX | Window | Why |
|-----|--------|-----|
| Low | 12:30-4:00 | Gamma already elevated, premium decayed |
| Moderate | 2:00-4:00 | Narrower window |
| High | 3:00-4:00 | Gamma doesn't spike until very late |

**Setup:**
1. Structural backstop (proven Volume Profile level)
2. Squeeze setup (price between structure and fly)
3. 15-25 wide fly, as close to ATM as possible
4. Cheap entry (late day, premium decayed)

**Example:**
- Entry: 20-wide @ $1.50, near ATM
- Move: 10-15 point burst
- Exit: $4-8 (2.5x-5x)

**Style:** Sniper - quick in/out, opportunistic

---

## Trade Selector Scoring

### Hard Filter

**Debit ≤ 10% of Width** (minimum 1:9 R2R) - applies to ALL campaigns

### Scoring Components

| Component | Weight | Description |
|-----------|--------|-------------|
| **Convexity** | 40% | PRIMARY: Is this trade significantly cheaper than nearby alternatives? |
| **R:R** | 25% | Relative to DTE expectations, not absolute |
| **Width Fit** | 20% | VIX regime alignment |
| **Gamma Alignment** | 15% | GEX structure positioning |

### Convexity Score (40%) - PRIMARY

The core metric: **finding trades significantly cheaper than nearby alternatives without sacrificing optionality**.

Sub-components:
- **Local Price Advantage (60%)**: Cheaper than same-width flies at adjacent strikes?
- **Statistical Anomaly (25%)**: Z-score below local average
- **Debit Efficiency (15%)**: Debit as % of width

### R:R Score (25%)

Scored relative to DTE expectations:

| DTE | Typical R2R | Exceptional |
|-----|-------------|-------------|
| 0-2 | 9-18 | 18+ |
| 3-5 | 15-30 | 30+ |
| 5-10 | 20-50 | 50+ |

---

## Capital Deployment

### Core Rule

**Max % of capital deployed per session** - regardless of campaigns or positions.

| Account Size | Max/Session |
|--------------|-------------|
| $25k | 1.0% |
| $50k | 0.8% |
| $100k | 0.6% |
| $250k | 0.4% |
| $500k+ | 0.3-0.5% |

**Why percentage decreases:** Larger accounts can diversify across more campaigns simultaneously.

**Any account can run all campaigns** - smaller accounts just manage frequency and exposure more carefully.

### Goal

- Low drawdowns
- Low volatility of returns
- Higher Sharpe ratio

---

## Volume Profile Analysis

### The Retail VP Fallacy

POC, VAH, VAL are **useless**:
- Arbitrary based on sampling timeframe
- Shift every time you add/remove data
- No mechanism for market to "know" these levels
- Market Profile holdovers that don't apply

### What Actually Matters: Market Memory

The **ONLY** thing that matters is what gets **repeated and remembered**.

### Volume Nodes (High Liquidity)

- Where the market discovers and maintains value
- Consolidation zones - market feels comfort here
- Boundaries persist and are respected in future visits
- All indentations, cracks, crevasses are remembered

**Behavior:** Price rotates, consolidates, mean-reverts inside nodes.

### Volume Wells (Low Liquidity)

- The **absence** of a node - an antinode
- Areas the market avoids (no value found)
- Low liquidity zones

**Behavior:** Price **trends** through wells. Candles elongate as market searches for next node.

### Structure = The Edges

Where high liquidity meets low liquidity:
- Top and bottom edges of nodes
- Walls of deep wells
- Every crack and crevasse in the profile

These edges form a **lattice of levels** that persist over time - not because of statistics, but because the market **remembers** where it found and rejected value.

### Breakouts

Occur when:
1. Price escapes a high-liquidity node
2. Enters a low-liquidity well
3. No value exists → market must search
4. Candles elongate until next node is found

---

## The Mandelbrot Foundation

### Markets Have Long Memory

- Price movements are NOT independent
- Past events influence future behavior over long horizons
- This is mathematically demonstrable

### Fractal Structure

- Markets exhibit self-similarity across scales
- Same structural patterns appear at different timeframes
- Volume profile topology is fractal

### Fat Tails / Power Laws

- Extreme events occur far more often than Gaussian models predict
- This is why convexity trades work
- Risk models based on normal distributions catastrophically underestimate tail events

---

## The Taleb Framework

### Fooled by Randomness

- Humans see patterns in noise
- Survivorship bias hides the graveyard
- Narrative fallacy explains random outcomes
- Most TA "patterns" are randomness misinterpreted

### Black Swans

- Rare events dominate outcomes
- Position for them, don't predict them
- The 50% of trades that lose are the cost of being positioned for tails

### Antifragility

- Don't just survive volatility - gain from it
- Multiple campaigns = antifragile portfolio
- High VIX is opportunity, not threat

### Convexity

- Payoffs that accelerate as moves get larger
- Small loss, large gain
- The core of every FOTW strategy

---

## The FOTW Edge

You're not predicting price. You're:

1. **Observing structure** (where market memory exists)
2. **Finding convexity** (where pricing is anomalous)
3. **Positioning asymmetrically** (risk small, make large)
4. **Preserving optionality** (never trapped)

This is **positioning for inevitability** with structures that gain from the chaos others fear.

---

## Summary

| Trap | FOTW Response |
|------|---------------|
| Pattern-matching on noise | Trade structure (Mandelbrot's proven memory) |
| Requiring prediction | Position for inevitability, don't predict |
| Needing to be "right" | Asymmetric payoffs - being wrong is cheap |
| Normal distribution assumptions | Assume fat tails, structure for them |
| Narrative explanations | Process over outcome |
| Technical Analysis voodoo | Market structure, convexity, asymmetry, fractals, optionality |
