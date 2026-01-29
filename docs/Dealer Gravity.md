# Dealer Gravity — A Structural Market Indicator (0DTE)

## Executive Summary

**Dealer Gravity** is not a prediction engine.  
It does not forecast price, project trends, or issue buy/sell signals.

Instead, it answers a simpler—and more honest—question:

> **Given how dealers are positioned and where real trading is occurring, where is price being structurally pulled to settle today?**

This indicator treats the market as a system of forces rather than a sequence of patterns.  
Price moves, but structure constrains it. Dealer Gravity makes those constraints visible.

![](image.png)

---

## What Dealer Gravity Shows

At every moment during the session, Dealer Gravity estimates:

- **Best Guess**  
  The price level the market is being pulled toward by dealer positioning and accepted liquidity.

- **High / Low Bounds**  
  Structural limits that define where price is likely to be caught if it escapes the center—based on options structure and real traded volume, not volatility statistics.

- **Confidence (Opacity Cloud)**  
  A background cloud that reflects how aligned or conflicted the market’s internal forces are.  
  Confidence never moves price; it only provides context.

Together, these elements describe **market gravity**, not direction.

---

## How It Thinks (Intuition, Not Math)

Dealer Gravity is built on three ideas:

1. **Dealers react, they don’t predict**  
   Options positioning creates zones where dealers are forced to hedge more aggressively. These zones act like gravitational basins for price—especially in 0DTE.

2. **Price must be able to trade there**  
   A level only matters if real volume has shown it can accept trades. Volume Profile data prevents the model from anchoring to theoretical levels that don’t actually transact.

3. **Spot activates structure**  
   Price moving through the field reveals which forces are active. Gravity is resolved relative to where spot is now—not where it was, and not where we hope it goes.

The result is a continuously updated picture of **where price wants to settle**, bounded by **where it can realistically go**, and conditioned by **how confident the structure is**.

---

## What This Indicator Is *Not*

- Not a trend indicator  
- Not a momentum oscillator  
- Not a volatility band  
- Not a VWAP variant  
- Not a close predictor  

It does not promise accuracy.  
It provides **structural awareness**.

---

## Update Cadence & Integrity

- Inputs update every **10–20 seconds**
- Structural truth is finalized and published **once per minute**
- No repainting
- No smoothing of the underlying data
- Visualization choices are strictly downstream

What you see is what the structure said *at that moment*.

---

## One-Sentence Description

> **Dealer Gravity reveals where price is being pulled to settle, how far it can realistically move away, and how aligned the market’s internal mechanics are—without predicting the future.**

---

---

## `gravity_worker` — Pseudo-Code Specification

### Purpose

Interpret live dealer structure and real traded volume to produce a one-minute structural gravity state for 0DTE markets.

---

### Inputs (Live Streams)

- Convexity Heatmap (options chain structure, 10–20s)
- GEX Model (dealer gamma exposure, 10–20s)
- Spot Price + Trade Volume (tick)
- Volume Profile Buckets (tick)

---

### Output (Authoritative Truth)

Published once per minute:

- Best Guess
- High Bound
- Low Bound
- Confidence (scalar, 0–1)

---

### High-Level Worker Loop

```pseudo
initialize worker
last_published_minute = None

loop continuously:
    now = current_time()

    heatmap = get_latest_heatmap()
    gex = get_latest_gex()
    spot = get_latest_spot()
    volume_profile = get_latest_volume_profile()

    if minute_has_closed(now, last_published_minute):
        gravity_state = compute_gravity_state(
            heatmap,
            gex,
            spot,
            volume_profile
        )

        publish(gravity_state)
        last_published_minute = current_minute(now)
```
---

### **Core Gravity Resolution**
```pseudo
function compute_gravity_state(heatmap, gex, spot, volume_profile):

    # 1. Extract candidate convexity basins
    basins = extract_convexity_basins(heatmap)

    # 2. Measure tradability via volume acceptance
    for basin in basins:
        basin.acceptance = compute_volume_acceptance(
            basin.price,
            volume_profile
        )

    # 3. Remove non-tradable (fantasy) levels
    tradable_basins = [
        basin for basin in basins
        if basin.acceptance >= MIN_ACCEPTANCE_THRESHOLD
    ]

    # 4. Resolve equilibrium (best guess)
    best_guess = select_equilibrium_basin(
        tradable_basins,
        spot,
        gex
    )

    # 5. Resolve structural bounds
    high = find_upper_bound(
        tradable_basins,
        best_guess,
        gex
    )

    low = find_lower_bound(
        tradable_basins,
        best_guess,
        gex
    )

    # 6. Compute confidence (orthogonal pass)
    confidence = compute_confidence(
        tradable_basins,
        best_guess,
        high,
        low,
        spot,
        gex,
        volume_profile
    )

    return {
        "ts": minute_close_timestamp(),
        "gravity": {
            "best": best_guess.price,
            "high": high.price,
            "low": low.price,
            "confidence": confidence
        }
    }
```
---

### **Supporting Concepts (Non-Exhaustive)**

**Convexity Basins** 
Clusters or peaks in the heatmap representing strong dealer positioning.

**Volume Acceptance** 
A measure of whether price has actually traded and been accepted at a level.

**Equilibrium Selection** 
The nearest reachable basin given current spot and dealer stiffness (GEX).

**Confidence** 
A scalar representing agreement between:

* dealer structure
* traded volume
* spot behavior
* temporal stability

Confidence provides context, not direction.

---

## **Design Principles**

* Structural, not predictive
* Deterministic and replayable
* No UI assumptions in the model
* Honest failure over fabricated output
* Built specifically for 0DTE dynamics

---

*Dealer Gravity doesn’t tell you what the market will do.*

*It shows you what the market is constrained to do.*