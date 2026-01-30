# MEL Model Definitions

## Overview

MEL (Model Effectiveness Layer) monitors five core models plus cross-model coherence. Each model answers a specific question about current market structure.

## Gamma / Dealer Positioning

**Question**: Are dealer hedging levels creating predictable price behavior?

**What It Measures**:
- Level respect rate: How often price reacts to dealer levels
- Mean reversion success: Whether price returns to expected levels
- Pin duration: Time spent at major dealer strikes
- Violation rate: How often price blows through levels
- Level stability: Consistency of dealer positioning

**VALID means**: Dealer levels are creating gravity, price respects hedging flows
**DEGRADED means**: Some levels working, others failing, mixed reliability
**REVOKED means**: Dealer levels are not influencing price, external forces dominate

## Volume Profile / Auction

**Question**: Is price accepting or rejecting value areas as expected?

**What It Measures**:
- HVN acceptance rate: Price finding acceptance in high volume areas
- LVN rejection rate: Price rejecting low volume areas
- Rotation completion: Balance area rotations completing normally
- Balance duration: Time maintaining equilibrium
- Initiative detection: Identifying directional moves vs. balance

**VALID means**: Auction theory is working, value areas are meaningful
**DEGRADED means**: Some auction behavior present, some anomalies
**REVOKED means**: Price ignoring volume structure, auction theory failing

## Liquidity / Microstructure

**Question**: Is order flow behaving predictably?

**What It Measures**:
- Absorption accuracy: Large orders being absorbed as expected
- Sweep predictiveness: Level sweeps leading to expected follow-through
- Slippage consistency: Execution matching expected fills
- Imbalance utility: Bid/ask imbalances predicting direction

**VALID means**: Order flow is readable, microstructure is normal
**DEGRADED means**: Some noise in order flow, reduced confidence
**REVOKED means**: Order flow is random or event-driven, not readable

## Volatility Regime

**Question**: Is the volatility environment consistent and measurable?

**What It Measures**:
- IV/RV alignment: Implied volatility matching realized movement
- Compression in balance: Vol compression during equilibrium
- Expansion with initiative: Vol expansion during directional moves
- Regime consistency: Stable volatility classification

**VALID means**: Volatility is behaving normally, options pricing is rational
**DEGRADED means**: Some vol anomalies, pricing partially reliable
**REVOKED means**: Volatility is unstable, event-driven, or mispriced

## Session Structure

**Question**: Is time-of-day behavior following normal patterns?

**What It Measures**:
- Open discovery: Morning price discovery proceeding normally
- Midday balance: Lunch hour equilibrium as expected
- Late resolution: End-of-day settlement patterns normal
- Liquidity windows: Expected liquidity at expected times

**VALID means**: Session patterns are predictable
**DEGRADED means**: Some disruption to normal session flow
**REVOKED means**: Session patterns completely disrupted

## Cross-Model Coherence

**Question**: Are the models agreeing or contradicting?

**States**:
- **STABLE**: Models in agreement, signals reinforce each other
- **MIXED**: Some disagreement, but not active contradiction
- **COLLAPSING**: Models actively contradicting each other
- **RECOVERED**: Recently returned to agreement after collapse

**Why It Matters**: When models agree, confidence is high. When they contradict, the market may be in transition or experiencing unusual conditions.

## Global Structure Integrity

Composite score (0-100%) combining all model effectiveness with coherence as a multiplier.

**Calculation**:
- Weighted average of five model scores
- Multiplied by coherence factor
- Weights reflect model importance

**Interpretation**:
- 70%+: Structure present, models trustworthy
- 50-69%: Partial structure, selective trust
- Below 50%: Structure absent, no-trade conditions
