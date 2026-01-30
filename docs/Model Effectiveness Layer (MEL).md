# Model Effectiveness Layer (MEL) — Technical Specification

## Executive Summary

The Model Effectiveness Layer (MEL) is a supervisory control system that continuously monitors whether market structure actually exists and to what degree analytical instruments are being respected in real time.

> *"MEL turns model trust from a feeling into a dataset."*
> — TraderDH

### The Apollo Analogy

NASA did not blindly trust instrument readings in an unpredictable environment. Instead, it ran **Caution & Warning** and **Failure Detection, Isolation, and Recovery (FDIR)** systems whose job was to answer a more fundamental question: *are the instruments themselves still valid?*

When sensors drifted or failed, they were flagged or suppressed, and pilots were explicitly told what **not** to trust.

Markets operate the same way:
- **Models are instruments**
- **Markets are hostile, non-stationary environments**
- **Instrument validity must be monitored continuously**

### Key Design Principle

> **If structure is absent, the strategy does not exist.**

MEL ensures this reality is acknowledged early, clearly, and unemotionally.

---

## The Problem MEL Solves

Current dashboards and model outputs fail in a predictable way:

1. **They always display information**, even when models are no longer valid
2. **On event or shock days**, structure collapses but instruments still appear "active"
3. **Traders interpret noise as signal**, mistaking randomness for edge

This leads to:
- Strategy breakdowns that feel inexplicable
- Forced discretionary decisions
- "Roll the dice" days with no formal acknowledgment that models have exited their domain

**The dangerous failure mode is not that models are "wrong," but that they are still consulted when they are no longer authoritative.**

MEL addresses this by explicitly detecting and declaring model degradation or invalidation.

---

## MEL Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Market Data Sources                                │
│         (Polygon, Options Chain, Order Flow, Volume Profile)                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MEL Calculation Engine                                │
│                                                                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │   Gamma     │ │   Volume    │ │  Liquidity  │ │ Volatility  │           │
│  │ Effectiveness│ │  Profile    │ │Effectiveness│ │Effectiveness│           │
│  │  Calculator │ │ Effectiveness│ │  Calculator │ │  Calculator │           │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘           │
│                                                                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────────┐           │
│  │  Session    │ │Cross-Model  │ │    Global Structure         │           │
│  │ Effectiveness│ │ Coherence   │ │    Integrity Calculator     │           │
│  │  Calculator │ │  Calculator │ │                             │           │
│  └─────────────┘ └─────────────┘ └─────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
┌─────────────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐
│    ADI Integration      │ │  MEL Database   │ │   UI Components         │
│                         │ │                 │ │                         │
│ - MEL scores in ADI     │ │ - Historical    │ │ - MEL Summary Dashboard │
│ - State in snapshots    │ │   snapshots     │ │ - Model Detail Screens  │
│ - Export formats        │ │ - Event flags   │ │ - Status Bar            │
└─────────────────────────┘ │ - Longitudinal  │ │ - Visual de-emphasis    │
                            │   analysis      │ └─────────────────────────┘
                            └─────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │      AI Commentary Service          │
                    │                                     │
                    │ - MEL state change triggers         │
                    │ - Model validity in context         │
                    │ - "Do not trust" warnings           │
                    └─────────────────────────────────────┘
```

---

## What MEL Monitors

MEL tracks the **effectiveness** (0–100%) of each analytical instrument based on expected vs observed behavior.

### 1. Gamma / Dealer Structure Effectiveness

**Purpose**: Determine if dealer gamma positioning is actually controlling price behavior.

**Expected Behaviors**:
| Metric | Description | Healthy Range |
|--------|-------------|---------------|
| Level Respect Rate | % of tests where price respects gamma levels | >70% |
| Mean Reversion Success | % of excursions that revert to gamma magnet | >75% |
| Pin Duration | Time spent at dominant gamma level | Strong/Medium/Weak |
| Violation Frequency | How often gamma levels are breached | Low/Medium/High |
| Violation Magnitude | Size of breaches when they occur | Contained/Extended |
| Gamma Level Stability | How much levels shift intraday | Stable/Shifting/Churning |
| Dealer Control Consistency | Overall dealer positioning coherence | High/Medium/Low |

**Failure/Stress Indicators**:
- Rapid Level Churn (levels shifting frequently)
- Large Impulse Ignoring Gamma (price moves through levels without reaction)
- Late-Day Breakdown (structure failing in final hour)
- Event Override Detected (FOMC/CPI overwhelming gamma)

**Time-of-Day Behavior**:
- Open (Discovery Phase): Normal/Chaotic/Extended
- Midday (Balance Phase): Stable/Fragile/Absent
- Late Session (Resolution): Structured/Unresolved/Breakdown

### 2. Volume Profile / Auction Structure Effectiveness

**Purpose**: Determine if auction theory is organizing price — or if balance/rotation logic has broken down.

**Expected Behaviors**:
| Metric | Description | Healthy Range |
|--------|-------------|---------------|
| HVN Acceptance | % of tests where price accepts at high volume nodes | >65% |
| LVN Rejection | % of tests where price rejects at low volume nodes | >60% |
| Rotation Completion | Whether rotations complete vs abort | Consistent/Inconsistent |
| Balance Duration | How long balance areas hold | Normal/Shortened/Extended |
| Initiative Follow-Through | Whether breakouts follow through | Strong/Mixed/Weak |

**Failure/Stress Indicators**:
- Poor Rotation Completion (rotations abort frequently)
- Balance Breakdown Frequency (balance areas failing)
- One-Time-Frame Control (single timeframe dominating)
- Trend Intrusions into Balance (balance constantly violated)

**Session Structure**:
- Open Auction: Normal/Extended/Failed
- Midday Balance: Stable/Fragile/Absent
- Late Session: Resolved/Unresolved/Chaotic

### 3. Liquidity / Microstructure Effectiveness

**Purpose**: Determine if microstructure signals are predictive or noise.

**Expected Behaviors**:
| Metric | Description | Healthy Range |
|--------|-------------|---------------|
| Absorption Accuracy | % of absorption signals that hold | >60% |
| Sweep Predictiveness | % of sweeps followed by continuation | >55% |
| Slippage vs Expectation | Actual vs expected fill quality | Normal/Elevated/Severe |
| Bid/Ask Imbalance Utility | Whether imbalance predicts direction | Useful/Mixed/Noise |

**Failure/Stress Indicators**:
- Liquidity Vacuum Events (sudden depth disappearance)
- Spread Widening (abnormal bid/ask spreads)
- Quote Stuffing / Instability
- Absorption Failures (absorbed levels giving way)

### 4. Volatility Regime Effectiveness

**Purpose**: Determine if volatility models (IV, RV, regime) are descriptive of actual behavior.

**Expected Behaviors**:
| Metric | Description | Healthy Range |
|--------|-------------|---------------|
| IV/RV Alignment | Implied vs realized volatility coherence | 0.7-1.3 ratio |
| Compression in Balance | Vol compresses during balance | Expected/Unexpected |
| Expansion with Initiative | Vol expands on breakouts | Expected/Unexpected |
| Regime Consistency | Regime doesn't flip rapidly | Stable/Transitioning/Chaotic |

**Failure/Stress Indicators**:
- IV/RV Divergence (implied wildly different from realized)
- Regime Whipsaw (rapid regime changes)
- Vol Smile Inversion (unusual skew behavior)
- Term Structure Inversion (unusual calendar behavior)

### 5. Session / Time-of-Day Effectiveness

**Purpose**: Determine if typical session structure is present.

**Expected Behaviors**:
| Metric | Description | Healthy Range |
|--------|-------------|---------------|
| Open Discovery | Normal price discovery at open | Normal/Extended/Absent |
| Midday Balance | Typical midday consolidation | Present/Fragile/Absent |
| Late Resolution | End-of-day directional resolution | Clear/Mixed/Chaotic |
| Liquidity Window Respect | MOC/VWAP windows behave normally | Yes/Partial/No |

**Failure/Stress Indicators**:
- Extended Discovery (open lasting too long)
- No Midday Balance (continuous trending)
- Late Chaos (no resolution, volatility spike)
- Liquidity Window Failure (MOC/VWAP abnormal)

### 6. Cross-Model Coherence

**Purpose**: Determine if models agree or contradict each other.

**Assessment**:
| State | Description |
|-------|-------------|
| STABLE | Models generally agree, signals reinforce |
| MIXED | Some disagreement, selective trust needed |
| COLLAPSING | Models contradict, no clear signal |
| RECOVERED | Previously collapsing, now stabilizing |

**Indicators**:
- Gamma says pin, VP says breakout → Contradiction
- Gamma, VP, Liquidity all agree → Coherence
- One model working while others fail → Asymmetric structure

### 7. Exogenous / Event Override Detection

**Purpose**: Detect when external events have overwhelmed structural models.

**Event Types**:
- Scheduled: FOMC, CPI, NFP, PCE, GDP, Earnings
- Unscheduled: Geopolitical shocks, Flash crashes, News bombs

**Detection Signals**:
- Simultaneous breakdown across models
- Unusual volume/volatility relative to norm
- Known event calendar match
- Sudden dominance of one-way flows

---

## MEL Outputs

### Per-Model Outputs

For each model, MEL produces:

| Output | Type | Description |
|--------|------|-------------|
| Effectiveness Score | 0-100% | Quantitative measure of model validity |
| Trend | ↑/→/↓ | Improving, Stable, or Degrading |
| State | VALID/DEGRADED/REVOKED | Categorical trust level |
| Confidence | High/Medium/Low | Confidence in the score itself |

### State Definitions

| State | Score Range | Meaning | UI Treatment |
|-------|-------------|---------|--------------|
| VALID | ≥70% | Model reliable, safe to use | Normal display |
| DEGRADED | 50-69% | Model accuracy reduced, use with caution | Warning indicator |
| REVOKED | <50% | Model unreliable, do not trust | Visual de-emphasis, no guidance |

### Global Structure Integrity

A weighted composite score answering: **"Does structure exist at all today?"**

```
Global Integrity = (
    0.30 × Gamma Effectiveness +
    0.25 × Volume Profile Effectiveness +
    0.20 × Liquidity Effectiveness +
    0.15 × Volatility Effectiveness +
    0.10 × Session Effectiveness
) × Coherence Multiplier
```

Where Coherence Multiplier:
- STABLE: 1.0
- MIXED: 0.85
- COLLAPSING: 0.60

**Interpretation**:
| Global Integrity | Interpretation |
|------------------|----------------|
| ≥70% | Structure present, models trustworthy |
| 50-69% | Partial structure, selective trust |
| <50% | Structure absent, no-trade conditions |

---

## MEL Data Model

### TypeScript Interface

```typescript
interface MELSnapshot {
  // Metadata
  timestamp_utc: string;
  snapshot_id: string;
  session: 'RTH' | 'ETH' | 'GLOBEX';
  event_flags: string[];

  // Individual Model Scores
  gamma: MELModelScore;
  volume_profile: MELModelScore;
  liquidity: MELModelScore;
  volatility: MELModelScore;
  session: MELModelScore;

  // Cross-Model
  cross_model_coherence: number;
  coherence_state: 'STABLE' | 'MIXED' | 'COLLAPSING' | 'RECOVERED';

  // Global
  global_structure_integrity: number;

  // Delta from previous
  delta?: MELDelta;
}

interface MELModelScore {
  effectiveness: number;          // 0-100
  trend: 'improving' | 'stable' | 'degrading';
  state: 'VALID' | 'DEGRADED' | 'REVOKED';
  confidence: 'high' | 'medium' | 'low';

  // Model-specific detail metrics
  detail: Record<string, number | string | boolean>;
}

interface MELDelta {
  gamma_effectiveness: number;
  volume_profile_effectiveness: number;
  liquidity_effectiveness: number;
  volatility_effectiveness: number;
  global_integrity: number;
}
```

### Python Dataclass

```python
from dataclasses import dataclass
from typing import Dict, List, Optional, Literal
from datetime import datetime

@dataclass
class MELModelScore:
    effectiveness: float  # 0-100
    trend: Literal['improving', 'stable', 'degrading']
    state: Literal['VALID', 'DEGRADED', 'REVOKED']
    confidence: Literal['high', 'medium', 'low']
    detail: Dict[str, any]

@dataclass
class MELSnapshot:
    timestamp_utc: datetime
    snapshot_id: str
    session: Literal['RTH', 'ETH', 'GLOBEX']
    event_flags: List[str]

    gamma: MELModelScore
    volume_profile: MELModelScore
    liquidity: MELModelScore
    volatility: MELModelScore
    session_structure: MELModelScore

    cross_model_coherence: float
    coherence_state: Literal['STABLE', 'MIXED', 'COLLAPSING', 'RECOVERED']

    global_structure_integrity: float

    delta: Optional[Dict[str, float]] = None
```

---

## MEL Calculation Engine

### File: `services/copilot/intel/mel.py`

```python
class MELCalculationEngine:
    """
    Model Effectiveness Layer calculation engine.
    Computes effectiveness scores for all market structure models.
    """

    # State thresholds
    VALID_THRESHOLD = 70
    DEGRADED_THRESHOLD = 50

    # Global integrity weights
    WEIGHTS = {
        'gamma': 0.30,
        'volume_profile': 0.25,
        'liquidity': 0.20,
        'volatility': 0.15,
        'session': 0.10,
    }

    COHERENCE_MULTIPLIERS = {
        'STABLE': 1.0,
        'MIXED': 0.85,
        'COLLAPSING': 0.60,
        'RECOVERED': 0.90,
    }

    def __init__(self, market_data, event_calendar, logger):
        self.market = market_data
        self.events = event_calendar
        self.logger = logger
        self.last_snapshot: Optional[MELSnapshot] = None
        self.history: List[MELSnapshot] = []

    def calculate_snapshot(self) -> MELSnapshot:
        """Calculate current MEL snapshot."""
        now = datetime.utcnow()

        # Calculate individual model scores
        gamma = self._calculate_gamma_effectiveness()
        volume_profile = self._calculate_volume_profile_effectiveness()
        liquidity = self._calculate_liquidity_effectiveness()
        volatility = self._calculate_volatility_effectiveness()
        session = self._calculate_session_effectiveness()

        # Calculate cross-model coherence
        coherence, coherence_state = self._calculate_coherence(
            gamma, volume_profile, liquidity, volatility, session
        )

        # Calculate global integrity
        global_integrity = self._calculate_global_integrity(
            gamma, volume_profile, liquidity, volatility, session,
            coherence_state
        )

        # Calculate delta from last snapshot
        delta = self._calculate_delta(
            gamma, volume_profile, liquidity, volatility, global_integrity
        )

        # Check for event overrides
        event_flags = self._check_event_flags(now)

        snapshot = MELSnapshot(
            timestamp_utc=now,
            snapshot_id=f"{now.isoformat()}_{len(self.history):04d}",
            session=self._determine_session(now),
            event_flags=event_flags,
            gamma=gamma,
            volume_profile=volume_profile,
            liquidity=liquidity,
            volatility=volatility,
            session_structure=session,
            cross_model_coherence=coherence,
            coherence_state=coherence_state,
            global_structure_integrity=global_integrity,
            delta=delta,
        )

        self.last_snapshot = snapshot
        self.history.append(snapshot)

        return snapshot

    def _calculate_gamma_effectiveness(self) -> MELModelScore:
        """
        Calculate gamma/dealer structure effectiveness.

        Measures:
        - Level respect rate
        - Mean reversion success
        - Pin duration
        - Violation frequency/magnitude
        - Gamma level stability
        - Dealer control consistency
        """
        detail = {}

        # Get gamma data
        gamma_data = self.market.get_gamma_structure()
        price_history = self.market.get_intraday_prices()

        # Calculate level respect rate
        level_tests = self._count_gamma_level_tests(price_history, gamma_data)
        level_respects = self._count_gamma_level_respects(price_history, gamma_data)
        detail['level_respect_rate'] = (level_respects / level_tests * 100) if level_tests > 0 else 0

        # Calculate mean reversion success
        excursions = self._identify_excursions(price_history, gamma_data)
        reversions = self._count_successful_reversions(excursions, gamma_data)
        detail['mean_reversion_success'] = (reversions / len(excursions) * 100) if excursions else 0

        # Calculate pin duration
        detail['pin_duration'] = self._calculate_pin_duration(price_history, gamma_data)

        # Calculate violation metrics
        violations = self._analyze_violations(price_history, gamma_data)
        detail['violation_frequency'] = violations['frequency']
        detail['violation_magnitude'] = violations['magnitude']

        # Calculate stability
        detail['gamma_level_stability'] = self._calculate_gamma_stability(gamma_data)

        # Calculate dealer control
        detail['dealer_control_consistency'] = self._calculate_dealer_control(gamma_data)

        # Composite effectiveness score
        effectiveness = (
            detail['level_respect_rate'] * 0.25 +
            detail['mean_reversion_success'] * 0.25 +
            self._score_pin_duration(detail['pin_duration']) * 0.15 +
            (100 - self._score_violation_frequency(detail['violation_frequency'])) * 0.15 +
            self._score_stability(detail['gamma_level_stability']) * 0.10 +
            self._score_dealer_control(detail['dealer_control_consistency']) * 0.10
        )

        return MELModelScore(
            effectiveness=effectiveness,
            trend=self._calculate_trend('gamma'),
            state=self._determine_state(effectiveness),
            confidence=self._determine_confidence(detail),
            detail=detail,
        )

    def _calculate_volume_profile_effectiveness(self) -> MELModelScore:
        """
        Calculate volume profile/auction effectiveness.

        Measures:
        - HVN acceptance rate
        - LVN rejection rate
        - Rotation completion
        - Balance duration
        - Initiative follow-through
        """
        detail = {}

        vp_data = self.market.get_volume_profile()
        price_history = self.market.get_intraday_prices()

        # HVN acceptance
        hvn_tests = self._count_hvn_tests(price_history, vp_data)
        hvn_accepts = self._count_hvn_accepts(price_history, vp_data)
        detail['hvn_acceptance'] = (hvn_accepts / hvn_tests * 100) if hvn_tests > 0 else 0

        # LVN rejection
        lvn_tests = self._count_lvn_tests(price_history, vp_data)
        lvn_rejects = self._count_lvn_rejects(price_history, vp_data)
        detail['lvn_rejection'] = (lvn_rejects / lvn_tests * 100) if lvn_tests > 0 else 0

        # Rotation completion
        detail['rotation_completion'] = self._analyze_rotations(price_history, vp_data)

        # Balance duration
        detail['balance_duration'] = self._analyze_balance_duration(price_history, vp_data)

        # Initiative follow-through
        detail['initiative_follow_through'] = self._analyze_initiative(price_history, vp_data)

        # Composite score
        effectiveness = (
            detail['hvn_acceptance'] * 0.25 +
            detail['lvn_rejection'] * 0.25 +
            self._score_rotation(detail['rotation_completion']) * 0.20 +
            self._score_balance(detail['balance_duration']) * 0.15 +
            self._score_initiative(detail['initiative_follow_through']) * 0.15
        )

        return MELModelScore(
            effectiveness=effectiveness,
            trend=self._calculate_trend('volume_profile'),
            state=self._determine_state(effectiveness),
            confidence=self._determine_confidence(detail),
            detail=detail,
        )

    def _calculate_global_integrity(
        self,
        gamma: MELModelScore,
        volume_profile: MELModelScore,
        liquidity: MELModelScore,
        volatility: MELModelScore,
        session: MELModelScore,
        coherence_state: str
    ) -> float:
        """Calculate Global Structure Integrity score."""
        weighted_sum = (
            self.WEIGHTS['gamma'] * gamma.effectiveness +
            self.WEIGHTS['volume_profile'] * volume_profile.effectiveness +
            self.WEIGHTS['liquidity'] * liquidity.effectiveness +
            self.WEIGHTS['volatility'] * volatility.effectiveness +
            self.WEIGHTS['session'] * session.effectiveness
        )

        multiplier = self.COHERENCE_MULTIPLIERS.get(coherence_state, 1.0)

        return weighted_sum * multiplier

    def _determine_state(self, effectiveness: float) -> str:
        """Determine model state from effectiveness score."""
        if effectiveness >= self.VALID_THRESHOLD:
            return 'VALID'
        elif effectiveness >= self.DEGRADED_THRESHOLD:
            return 'DEGRADED'
        else:
            return 'REVOKED'

    # ... additional calculation methods
```

---

## MEL API Endpoints

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/mel/snapshot | Get current MEL snapshot |
| GET | /api/mel/gamma | Get gamma effectiveness detail |
| GET | /api/mel/volume-profile | Get volume profile effectiveness detail |
| GET | /api/mel/liquidity | Get liquidity effectiveness detail |
| GET | /api/mel/volatility | Get volatility effectiveness detail |
| GET | /api/mel/session | Get session effectiveness detail |
| GET | /api/mel/history | Get historical MEL snapshots |
| GET | /api/mel/history?date=YYYY-MM-DD | Get MEL history for specific date |

### Response Format

**GET /api/mel/snapshot**:
```json
{
  "timestamp_utc": "2026-01-29T21:05:00Z",
  "snapshot_id": "2026-01-29T21:05:00Z_0042",
  "session": "RTH",
  "event_flags": ["FOMC"],

  "gamma": {
    "effectiveness": 82,
    "trend": "improving",
    "state": "VALID",
    "confidence": "high"
  },
  "volume_profile": {
    "effectiveness": 61,
    "trend": "stable",
    "state": "DEGRADED",
    "confidence": "medium"
  },
  "liquidity": {
    "effectiveness": 35,
    "trend": "degrading",
    "state": "REVOKED",
    "confidence": "medium"
  },
  "volatility": {
    "effectiveness": 28,
    "trend": "degrading",
    "state": "REVOKED",
    "confidence": "low"
  },
  "session_structure": {
    "effectiveness": 57,
    "trend": "stable",
    "state": "DEGRADED",
    "confidence": "medium"
  },

  "cross_model_coherence": 33,
  "coherence_state": "COLLAPSING",

  "global_structure_integrity": 42,

  "delta": {
    "gamma_effectiveness": 2.5,
    "volume_profile_effectiveness": -1.2,
    "global_integrity": -0.09
  }
}
```

---

## MEL UI Components

### 1. MEL Summary Dashboard

The primary interface showing effectiveness percentages for each model at a glance.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MEL SCORES                                      │
│                      MODEL EFFECTIVENESS LAYER                               │
│                    Are Market Models Valid Today?                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Gamma / Dealer Positioning      84% ████████████████░░░░ VALID      ▲      │
│  Volume Profile / Auction        62% ████████████░░░░░░░░ DEGRADED   →      │
│  Liquidity / Microstructure      35% ███████░░░░░░░░░░░░░ REVOKED    ▼      │
│  Volatility Regime               28% █████░░░░░░░░░░░░░░░ REVOKED    ▼      │
│  Session / Time-of-Day           57% ███████████░░░░░░░░░ MIXED      →      │
│  Cross-Model Coherence           33% ██████░░░░░░░░░░░░░░ COLLAPSING ▼      │
│                                                                              │
│                         ┌─────────────────┐                                  │
│                         │      42%        │                                  │
│                         │    GLOBAL       │                                  │
│                         │   STRUCTURE     │                                  │
│                         │   INTEGRITY     │                                  │
│                         └─────────────────┘                                  │
│                                                                              │
│  EVENT FLAGS: [FOMC]                     SESSION: RTH | DTE: 0              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2. MEL Status Bar (Compact)

For embedding in main workspace header:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ MEL: 42% │ Γ:84✓ │ VP:62⚠ │ LIQ:35✗ │ VOL:28✗ │ SES:57⚠ │ COH:33↓ │ [FOMC] │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3. MEL Detail Screen — Gamma

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GAMMA / DEALER STRUCTURE — DETAIL                         │
│                       Model Effectiveness Layer                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CURRENT EFFECTIVENESS SCORE ........... 82%   VALID                        │
│  TREND ................................. ↑     Improving                    │
│  CONFIDENCE ............................ High                               │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  EXPECTED GAMMA BEHAVIORS (TODAY)                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Level Respect Rate .................... 79%  ████████████████░░░░          │
│  Mean Reversion Success ................ 86%  █████████████████░░░          │
│  Pin Duration (dominant level) ......... Strong                             │
│  Violation Frequency ................... Low                                │
│  Violation Magnitude ................... Contained                          │
│  Gamma Level Stability ................. Stable                             │
│  Dealer Control Consistency ............ High                               │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  FAILURE / STRESS INDICATORS                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Rapid Level Churn ..................... No   ✓                             │
│  Large Impulse Ignoring Gamma .......... No   ✓                             │
│  Late-Day Breakdown .................... No   ✓                             │
│  Event Override Detected ............... No   ✓                             │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  TIME-OF-DAY BEHAVIOR                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Open (Discovery Phase) ................ Normal                             │
│  Midday (Balance Phase) ................ Stable                             │
│  Late Session (Resolution) ............. Structured                         │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  GAMMA STATE SUMMARY                                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  STATUS: STRUCTURE IN CONTROL                                                │
│  GUIDANCE: Gamma levels are authoritative. Structural behavior is intact.   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4. Visual De-Emphasis (REVOKED State)

When a model is REVOKED, its associated UI widgets should be visually de-emphasized:

```css
/* Normal widget */
.widget {
  opacity: 1.0;
  border: 1px solid #333;
}

/* DEGRADED model widget */
.widget.mel-degraded {
  opacity: 0.85;
  border: 1px solid #f59e0b;
}
.widget.mel-degraded::before {
  content: "⚠ DEGRADED";
  /* warning badge */
}

/* REVOKED model widget */
.widget.mel-revoked {
  opacity: 0.5;
  border: 1px solid #ef4444;
  filter: grayscale(30%);
}
.widget.mel-revoked::before {
  content: "✗ REVOKED - Do Not Trust";
  /* prominent warning */
}
```

**Hard Design Rule**: If a model is REVOKED:
- Its detail screen becomes read-only
- No interpretive guidance is shown
- The system explicitly says: *"This instrument is not valid today"*

---

## MEL + AI Commentary Integration

### MEL-Specific Commentary Triggers

```typescript
type MELCommentaryTrigger =
  | { type: 'mel_state_change'; model: string; from: string; to: string; score: number }
  | { type: 'global_integrity_warning'; score: number; threshold: number }
  | { type: 'coherence_collapse'; from: string; to: string }
  | { type: 'event_override_detected'; event: string; models_affected: string[] };
```

### Commentary Examples

**State Change**:
> "Gamma model transitioned from VALID to DEGRADED (82% → 64%). Level respect rate declining — price ignoring gamma walls more frequently."

**Global Integrity Warning**:
> "Global Structure Integrity at 42%. Three models REVOKED. Structure may be absent today."

**Coherence Collapse**:
> "Cross-model coherence COLLAPSING. Gamma suggests pin at 6950, Volume Profile suggests breakout. Models contradicting."

**Event Override**:
> "FOMC detected. Liquidity and Volatility models automatically flagged. External flows likely overwhelming structural models."

### AI Should Reference MEL States

When generating any commentary, the AI should:
1. Check MEL states before discussing model outputs
2. Note when a model is DEGRADED or REVOKED
3. Avoid referencing REVOKED model outputs as authoritative

**Good**:
> "Spot is 18 points below zero gamma (6947). Gamma model is VALID (82%), levels should be authoritative."

**Bad**:
> "Spot is 18 points below zero gamma (6947)." *(When gamma is REVOKED)*

---

## MEL Historical Database

### Purpose

Once MEL is running continuously, it creates a high-value historical database that goes beyond price history to store **model validity over time**.

### Schema

```sql
CREATE TABLE mel_snapshots (
    id TEXT PRIMARY KEY,
    timestamp_utc TEXT NOT NULL,
    session TEXT NOT NULL,

    -- Individual scores
    gamma_effectiveness REAL,
    gamma_state TEXT,
    volume_profile_effectiveness REAL,
    volume_profile_state TEXT,
    liquidity_effectiveness REAL,
    liquidity_state TEXT,
    volatility_effectiveness REAL,
    volatility_state TEXT,
    session_effectiveness REAL,
    session_state TEXT,

    -- Cross-model
    cross_model_coherence REAL,
    coherence_state TEXT,

    -- Global
    global_structure_integrity REAL,

    -- Context
    event_flags TEXT,  -- JSON array
    detail JSON,       -- Full detail metrics

    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_mel_timestamp ON mel_snapshots(timestamp_utc);
CREATE INDEX idx_mel_global ON mel_snapshots(global_structure_integrity);
CREATE INDEX idx_mel_events ON mel_snapshots(event_flags);
```

### What We Can Learn

Over time, MEL enables:

1. **Structure Frequency**: How often does structure actually exist?
2. **Model Robustness**: Which models are most reliable and when?
3. **Event Impact**: Which events reliably invalidate structure?
4. **Seasonality**: Patterns in structure presence (day of week, time of month)
5. **Failure Sequencing**: Which models fail first? (Leading indicators)
6. **Recovery Patterns**: How quickly does structure return after events?

### Strategic Value

The MEL database allows evolution from:

> *"Is structure present right now?"*

to:

> *"How likely is structure to persist today, given historical context?"*

**Without crossing into prediction.**

---

## Implementation Phases

### Phase 1: MEL Foundation
- [ ] Define MEL data model (TypeScript + Python)
- [ ] Implement Gamma effectiveness calculator
- [ ] Implement Volume Profile effectiveness calculator
- [ ] Create MEL snapshot generator
- [ ] Add MEL to ADI integration
- [ ] Build MEL Summary Dashboard UI
- [ ] Add MEL Status Bar to main workspace

### Phase 2: Additional Models
- [ ] Implement Liquidity effectiveness calculator
- [ ] Implement Volatility effectiveness calculator
- [ ] Implement Session effectiveness calculator
- [ ] Implement Cross-Model Coherence calculator
- [ ] Build Model Detail Screens (Gamma, VP)

### Phase 3: AI Integration
- [ ] Add MEL state change triggers to Commentary
- [ ] Update AI prompts to reference MEL states
- [ ] Implement "Do not trust" warnings
- [ ] Add Global Integrity warnings

### Phase 4: Visual Enforcement
- [ ] Implement visual de-emphasis for DEGRADED widgets
- [ ] Implement visual de-emphasis for REVOKED widgets
- [ ] Make REVOKED detail screens read-only
- [ ] Remove interpretive guidance when REVOKED

### Phase 5: Historical + Longitudinal
- [ ] Create MEL historical database
- [ ] Build MEL history API endpoints
- [ ] Create historical analysis tools
- [ ] Event impact analysis
- [ ] Seasonality detection

---

## Configuration

**Environment Variables**:
```bash
MEL_ENABLED=true
MEL_VALID_THRESHOLD=70
MEL_DEGRADED_THRESHOLD=50
MEL_SNAPSHOT_INTERVAL_MS=5000
MEL_HISTORY_RETENTION_DAYS=365
```

**truth/components/mel.json**:
```json
{
  "mel": {
    "enabled": true,
    "thresholds": {
      "valid": 70,
      "degraded": 50
    },
    "weights": {
      "gamma": 0.30,
      "volume_profile": 0.25,
      "liquidity": 0.20,
      "volatility": 0.15,
      "session": 0.10
    },
    "coherence_multipliers": {
      "STABLE": 1.0,
      "MIXED": 0.85,
      "COLLAPSING": 0.60,
      "RECOVERED": 0.90
    },
    "snapshotIntervalMs": 5000,
    "historyRetentionDays": 365,
    "alertOnRevoked": true,
    "visualDeEmphasis": true
  }
}
```

---

## File Structure

```
services/copilot/
├── intel/
│   ├── mel.py                     # MEL calculation engine
│   ├── mel_gamma.py               # Gamma effectiveness calculator
│   ├── mel_volume_profile.py      # Volume profile calculator
│   ├── mel_liquidity.py           # Liquidity calculator
│   ├── mel_volatility.py          # Volatility calculator
│   ├── mel_session.py             # Session calculator
│   ├── mel_coherence.py           # Cross-model coherence
│   ├── mel_database.py            # Historical storage
│   └── mel_api.py                 # API endpoints
└── tests/
    ├── test_mel.py
    ├── test_mel_gamma.py
    └── test_mel_integration.py

ui/src/
├── components/
│   ├── MELDashboard.tsx           # Summary dashboard
│   ├── MELStatusBar.tsx           # Compact status bar
│   ├── MELDetailScreen.tsx        # Generic detail screen
│   ├── MELGammaDetail.tsx         # Gamma-specific detail
│   └── MELVolumeProfileDetail.tsx # VP-specific detail
├── hooks/
│   └── useMEL.ts                  # MEL data fetching
└── styles/
    └── mel.css                    # MEL-specific styles
```

---

## Key Constraints

1. **MEL outputs trust, not trades.** It governs confidence in instruments, not trading decisions.

2. **If structure is absent, the strategy does not exist.** MEL ensures this is acknowledged.

3. **REVOKED means do not trust.** No interpretive guidance. Read-only display. Explicit warning.

4. **Dashboards must not lie by omission.** When models are invalid, the UI must show it.

5. **Professional alignment.** MEL formalizes what professional desks do implicitly — standing aside when structure is absent.

---

## Closing Statement

> *"Confusion becomes classification. Chaos becomes detectable. Silence becomes a signal. Dashboards stop lying by omission."*

MEL turns model failure into **first-class information**, which is the missing layer in most trading systems.

---

*Specification based on original MEL concept by TraderDH (David Henderson), January 2026.*
