# Alert Manager - Unified Workflow Awareness System

## Philosophy

The Alert Manager is not simply a "price alert tool" - it is the **awareness layer** that helps traders embrace the full left-to-right architecture of FOTW (Flight of the Wizard). Through AI-powered natural language prompts, traders can express any condition they want to be aware of - from technical price levels to behavioral patterns to workflow habits.

Alerts reinforce good trading process by creating awareness at every stage:
- **Before trading**: Am I prepared? Have I done my routine?
- **During trading**: Is my position behaving as expected?
- **After trading**: Did I reflect? Did I learn?

---

## Core Principle: Prompt-First Design

**Prompt alerts are THE primary creation paradigm**, not a category alongside others.

Natural language can express:
- Threshold conditions: *"Alert me when SPX crosses 6000"*
- Risk conditions: *"Let me know if gamma starts eating into my profit zone"*
- Workflow triggers: *"Remind me to journal after closing a trade"*
- Behavioral patterns: *"Notice if I'm revenge trading after a loss"*
- Conditions without predefined types: *"Alert me if this position starts behaving differently than when I entered"*

The AI parses intent and either:
1. Maps to an existing alert type (price, debit, AI theta/gamma, etc.)
2. Evaluates directly against reference state using semantic understanding
3. Creates a workflow trigger tied to events rather than market data

---

## Alert Spectrum

The Alert Manager covers the full spectrum from simple to sophisticated:

```
Simple                                                           Sophisticated
   │                                                                    │
   ▼                                                                    ▼
┌────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌──────────┐
│Threshold│   │   Algo/    │   │     AI     │   │  Workflow  │   │  Prompt  │
│ Alerts  │   │   Rules    │   │   Alerts   │   │   Alerts   │   │  Alerts  │
│         │   │            │   │            │   │            │   │          │
│ Price   │   │ Max Loss   │   │ Theta/     │   │ Routine    │   │ Natural  │
│ Debit   │   │ Position   │   │ Gamma      │   │ Process    │   │ Language │
│ Target  │   │ Limits     │   │ Sentiment  │   │ Retro-     │   │ Any      │
│ Stop    │   │ Delta      │   │ Risk Zone  │   │ spective   │   │ Intent   │
│ Time    │   │ Rules      │   │ Butterfly  │   │            │   │          │
└────────┘   └────────────┘   └────────────┘   └────────────┘   └──────────┘
     │              │               │                │               │
     └──────────────┴───────────────┴────────────────┴───────────────┘
                                    │
                           All expressible via
                           natural language prompt
```

**Key insight**: Prompt alerts can express ANY of these. A trader can say:
- *"Alert me when SPX goes above 6000"* → Creates threshold alert
- *"Warn me if I'm about to exceed my daily loss limit"* → Creates algo rule alert
- *"Tell me when gamma risk is getting dangerous"* → Creates AI alert
- *"Remind me to journal after trades"* → Creates workflow alert

The prompt interface is the **universal entry point**. The system figures out the right implementation.

---

## FOTW Workflow Integration

The Alert Manager spans the entire left-to-right trading workflow:

```
┌─────────────┐     ┌─────────────────────────────────┐     ┌─────────────┐
│   ROUTINE   │ --> │      ANALYSIS / SELECTION       │ --> │   PROCESS   │
│   (Warm)    │     │         ACTION                  │     │   (Cool)    │
│             │     │                                 │     │             │
│ Preparation │     │  Trading Activity               │     │ Reflection  │
│ Grounding   │     │  Position Management            │     │ Learning    │
└─────────────┘     └─────────────────────────────────┘     └─────────────┘
      │                          │                                │
      ▼                          ▼                                ▼
  Routine Alerts           Trading Alerts                  Process Alerts
  - Pre-market prep        - Price/Debit                   - Journal prompts
  - Checklist reminders    - AI Theta/Gamma                - Playbook updates
  - Readiness checks       - Butterfly Entry/Mgmt          - Pattern review
                           - Risk Zone                     - Retrospective
```

### Alert Categories by Workflow Stage

| Stage | Alert Purpose | Example Prompts |
|-------|---------------|-----------------|
| **Routine** | Preparation & grounding | "Remind me to check VIX regime before my first trade" |
| | | "Alert if I haven't reviewed overnight action by 9:15 AM" |
| | | "Notice if I'm about to trade without completing my checklist" |
| **Analysis** | Market structure awareness | "Alert me when we approach a major GEX level" |
| | | "Let me know if market mode shifts to expansion" |
| **Selection** | Trade idea validation | "Alert if this setup doesn't match my playbook criteria" |
| | | "Warn me if I'm considering a trade outside my edge" |
| **Action** | Position management | "Alert if gamma starts eating into profit near expiration" |
| | | "Tell me when my butterfly reaches 50% of max profit" |
| | | "Warn if my position risk exceeds entry parameters" |
| **Process** | Reflection & learning | "Prompt me to journal after closing any trade" |
| | | "Remind me to update playbook after a losing trade" |
| | | "Ask me what I learned before I close the app" |
| **Retrospective** | Pattern recognition | "Notice if I'm repeating a pattern from last week" |
| | | "Alert if this setup resembles one that failed before" |
| | | "Track if I'm honoring my stated trading rules" |

---

## Algo/Rule Enforcement

A critical function of the Alert Manager is **enforcing trading discipline** through automated rule monitoring. Traders define their rules, and the system holds them accountable.

### Pre-Trade Rules (Gate Checks)
Alerts that fire BEFORE a trade is entered, enforcing entry criteria:

| Rule | Example Prompt |
|------|----------------|
| Position sizing | *"Warn me if I'm about to risk more than 2% on a single trade"* |
| Daily trade limit | *"Block me after 3 trades in a day"* |
| Loss limit gate | *"Don't let me trade if I'm down more than $500 today"* |
| Setup validation | *"Alert if this entry doesn't match my playbook criteria"* |
| Time restrictions | *"Warn me if I'm trading in the last 30 minutes"* |
| Correlation check | *"Alert if this trade is too correlated with my existing positions"* |

### Active Position Rules (Ongoing Monitoring)
Alerts that monitor open positions against defined parameters:

| Rule | Example Prompt |
|------|----------------|
| Delta limits | *"Alert if my portfolio delta exceeds +/- 50"* |
| Gamma exposure | *"Warn when gamma risk gets too high near expiration"* |
| Theta decay | *"Tell me if I'm losing more than $100/day to theta"* |
| Buying power | *"Alert at 70% buying power utilization"* |
| Profit targets | *"Notify at 50%, warn at 75%, close at 100% of max profit"* |
| Time stops | *"Exit reminder if position is open past 2 PM"* |

### Post-Trade Rules (Behavioral Patterns)
Alerts that detect behavioral patterns after trades:

| Rule | Example Prompt |
|------|----------------|
| Revenge trading | *"Notice if I'm entering a trade within 10 minutes of a loss"* |
| Overtrading | *"Warn if I've made more than 5 trades today"* |
| Rule violations | *"Track how often I break my own entry rules"* |
| Win/loss streaks | *"Alert after 3 consecutive losses"* |
| Time patterns | *"Notice if I'm trading during times I historically lose"* |

### Rule Severity Levels

Rules can be configured with different enforcement levels:

| Level | Behavior |
|-------|----------|
| **Inform** | Silent log, visible in retrospective |
| **Notify** | Visual notification, no interruption |
| **Warn** | Prominent warning requiring acknowledgment |
| **Block** | Prevents action until override (with reason) |

---

## Vexy AI: The Meta-Alert Layer

Vexy doesn't just process individual alerts - she **monitors the alert system itself** and provides higher-order awareness. She is the voice that synthesizes what all the alerts are collectively saying.

### Meta-Alert Functions

| Function | Description | Example |
|----------|-------------|---------|
| **Synthesis** | Combines signals from multiple alerts | *"Your gamma alert, theta alert, and time alert are all warning - this position needs attention"* |
| **Pattern Detection** | Notices patterns in alert activity | *"This alert pattern looks like last Tuesday before your drawdown"* |
| **Alert Fatigue** | Monitors trader response to alerts | *"You've dismissed 8 alerts today without action - are you paying attention?"* |
| **Contradiction Detection** | Spots conflicting signals | *"Your entry alert says go, but your risk alerts say wait"* |
| **Coaching** | Reminds of stated intentions | *"You set a rule to stop after 3 losses. This would be trade #4."* |
| **Proactive Warning** | Anticipates before alerts fire | *"Based on current trajectory, your gamma alert will trigger in ~15 minutes"* |
| **Contextual Priority** | Highlights what matters now | *"Ignore the routine alerts - focus on your expiring position"* |

### Vexy Commentary Integration

Vexy's epoch and event commentary already exists. The meta-alert layer adds:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 🎙️ Vexy                                                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ EPOCH: "Compression regime with low VIX. Gamma scalp conditions."       │
│                                                                         │
│ EVENT: "Your 6000 butterfly just crossed 50% profit. Two alerts are     │
│         watching this position - both suggest tightening stops."        │
│                                                                         │
│ META: "You've triggered 3 profit alerts this week and let all of them   │
│        run to loss. Consider honoring your rules this time."            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Meta-Alert Types

| Type | Trigger | Purpose |
|------|---------|---------|
| `alert_cluster` | Multiple alerts fire together | Systemic issue detection |
| `alert_ignored` | Trader dismisses without action | Accountability nudge |
| `alert_pattern` | Historical pattern match | Learning reinforcement |
| `alert_conflict` | Contradictory alert signals | Decision support |
| `alert_fatigue` | High dismiss rate | Attention check |
| `alert_prediction` | Trajectory analysis | Proactive warning |
| `rule_reminder` | Approaching stated limit | Discipline enforcement |

### Implementation

Vexy's meta-alert processing runs in the slow loop alongside AI alerts:

```python
class VexyMetaAlertProcessor:
    """
    Monitors the alert system itself and generates meta-commentary.
    """

    async def evaluate_alert_state(self, alerts: List[Alert], history: AlertHistory) -> MetaCommentary:
        # Cluster detection - multiple alerts firing together
        active_warnings = [a for a in alerts if a.stage in ('warn', 'triggered')]
        if len(active_warnings) >= 3:
            return self.generate_cluster_commentary(active_warnings)

        # Pattern matching - compare to historical alert patterns
        pattern_match = await self.find_historical_pattern(alerts, history)
        if pattern_match and pattern_match.confidence > 0.7:
            return self.generate_pattern_commentary(pattern_match)

        # Fatigue detection - high dismiss rate
        recent_dismissals = history.get_dismissals(hours=4)
        if len(recent_dismissals) > 5:
            return self.generate_fatigue_commentary(recent_dismissals)

        # Rule adherence - approaching limits
        rule_status = await self.check_rule_proximity(alerts)
        if rule_status.approaching_limit:
            return self.generate_rule_reminder(rule_status)

        return None
```

### Vexy as Trading Coach

With meta-alert awareness, Vexy becomes a **trading coach** who:

1. **Sees the forest, not just trees** - Individual alerts are data points; Vexy sees the picture
2. **Remembers your history** - Connects current patterns to past outcomes
3. **Holds you accountable** - Reminds you of rules you set for yourself
4. **Adapts to your style** - Learns when you need a nudge vs. when to stay quiet
5. **Provides synthesis** - "Here's what your alerts are collectively telling you"

This transforms the alert system from reactive notifications into **proactive trading guidance**.

---

## Service Architecture

### Backend Services

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Alert Manager Service                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐    │
│  │   Journal    │   │   Copilot    │   │      Vexy AI         │    │
│  │   Service    │   │   Service    │   │   (Prompt Engine)    │    │
│  │              │   │              │   │                      │    │
│  │ - CRUD API   │   │ - Fast Loop  │   │ - Prompt Parser      │    │
│  │ - Persistence│   │ - Slow Loop  │   │ - Semantic Zones     │    │
│  │ - History    │   │ - Evaluators │   │ - Reference State    │    │
│  └──────┬───────┘   └──────┬───────┘   │ - Stage Transitions  │    │
│         │                  │           └──────────┬───────────┘    │
│         │                  │                      │                │
│         └──────────────────┼──────────────────────┘                │
│                            │                                        │
│                     ┌──────▼───────┐                               │
│                     │    Redis     │                               │
│                     │   Pub/Sub    │                               │
│                     │              │                               │
│                     │ - Sync       │                               │
│                     │ - Events     │                               │
│                     │ - SSE Bridge │                               │
│                     └──────────────┘                               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/alerts` | GET | Fetch all alerts for user |
| `/api/alerts` | POST | Create alert (parsed from prompt) |
| `/api/alerts/:id` | PATCH | Update alert |
| `/api/alerts/:id` | DELETE | Delete alert |
| `/api/prompt-alerts` | GET | Fetch prompt alerts with reference state |
| `/api/prompt-alerts` | POST | Create prompt alert (AI parses intent) |
| `/api/prompt-alerts/:id/parse` | POST | Re-parse prompt after edit |
| `/api/alerts/:id/evaluate` | POST | Request AI evaluation |
| `/sse/alerts` | SSE | Real-time alert events |

### Prompt Alert Lifecycle

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  WATCHING   │ --> │   UPDATE    │ --> │    WARN     │ --> │ ACCOMPLISHED│
│             │     │             │     │             │     │             │
│ Monitoring  │     │ Informing   │     │ Attention   │     │ Objective   │
│ passively   │     │ of change   │     │ may be      │     │ met         │
│             │     │             │     │ needed      │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

Stage transitions are AI-driven based on:
- Comparison of current state to reference state
- Semantic understanding of trader's prompt intent
- Confidence threshold (low: 40%, medium: 60%, high: 80%)

---

## Alert Types

### Basic Threshold Alerts (Traditional)

Standard alerts typical of any trading system. Simple, fast, deterministic.

| Type | Evaluator | Description |
|------|-----------|-------------|
| `price` | Fast Loop | Spot price crosses level (above/below/at) |
| `price_range` | Fast Loop | Price exits or enters a range |
| `debit` | Fast Loop | Position debit crosses level |
| `profit_target` | Fast Loop | Profit reaches target percentage |
| `stop_loss` | Fast Loop | Loss reaches stop percentage |
| `trailing_stop` | Fast Loop | Trailing stop triggered (high water mark - %) |
| `time_boundary` | Fast Loop | EOD/EOW/EOM time-based alerts |
| `dte_warning` | Fast Loop | Days to expiration threshold |
| `volume_spike` | Fast Loop | Unusual volume detected |
| `vix_level` | Fast Loop | VIX crosses threshold |

### Algo/Strategy Rule Alerts

Automated enforcement of trading strategy rules and risk parameters.

| Type | Evaluator | Description |
|------|-----------|-------------|
| `max_position_size` | Fast Loop | Position size exceeds limit |
| `max_daily_loss` | Fast Loop | Daily P&L breaches max loss |
| `max_daily_trades` | Fast Loop | Trade count exceeds limit |
| `correlation_limit` | Slow Loop | Portfolio correlation too high |
| `delta_limit` | Fast Loop | Net delta exceeds threshold |
| `gamma_exposure` | Fast Loop | Gamma risk exceeds limit |
| `theta_burn_rate` | Fast Loop | Daily theta decay warning |
| `buying_power_usage` | Fast Loop | BP utilization threshold |
| `concentration_risk` | Slow Loop | Too much in single underlying |
| `strategy_deviation` | Slow Loop | Position deviates from playbook parameters |
| `entry_rule_violation` | Event | Trade entry doesn't match stated criteria |
| `risk_reward_check` | Event | R:R ratio below minimum |

### AI-Powered Alerts

Intelligent evaluation using market context and strategy analysis.

| Type | Evaluator | Description |
|------|-----------|-------------|
| `ai_theta_gamma` | Slow Loop | AI-computed dynamic risk zone |
| `ai_sentiment` | Slow Loop | AI market sentiment analysis |
| `ai_risk_zone` | Slow Loop | AI-computed risk boundaries |
| `butterfly_entry` | Slow Loop | OTM butterfly entry detection |
| `butterfly_profit_mgmt` | Slow Loop | Butterfly profit management |
| `prompt_driven` | Slow Loop | Natural language evaluated by AI |
| `pattern_recognition` | Slow Loop | Chart/setup pattern detection |
| `regime_change` | Slow Loop | Market regime transition detected |

### Workflow Alerts (Event-Attached)

| Type | Trigger | Description |
|------|---------|-------------|
| `routine_reminder` | Time/Event | Pre-market preparation prompts |
| `routine_checklist` | Checklist State | Incomplete checklist warnings |
| `process_journal` | Trade Close | Post-trade journaling prompts |
| `process_playbook` | Trade Outcome | Playbook update reminders |
| `retrospective_pattern` | Pattern Match | Behavioral pattern detection |
| `retrospective_rule` | Rule Violation | Trading rule adherence check |

---

## UI Design

### Drawer Structure

The Alert Manager is a bottom-centered drawer that provides unified access to all alerts.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Alert Manager                                                         [×]   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  What do you want to be aware of?                                       │ │
│  │  ┌───────────────────────────────────────────────────────────────────┐  │ │
│  │  │ Describe in natural language...                                   │  │ │
│  │  │                                                                   │  │ │
│  │  └───────────────────────────────────────────────────────────────────┘  │ │
│  │  [Create Alert]                                        Context: [Auto ▼] │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  View: [All] [Routine] [Trading] [Process] [Triggered]           [Settings] │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ "Alert me if gamma starts eating into my profit zone"    ⚡ Watching   │  │
│  │   SPX 6000 BF  |  Confidence: Medium  |  Created: Feb 7, 9:30 AM      │  │
│  │   Reference: Gamma 0.0012, Profit $450                          [⋮]   │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ "Remind me to journal after closing a trade"             ○ Process     │  │
│  │   Triggers on: Trade Close  |  Last: Never                      [⋮]   │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ "Check VIX regime before first trade"                    ✓ Completed   │  │
│  │   Routine  |  Completed: 9:28 AM                                [⋮]   │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Creation Flow

1. User types natural language prompt in the input area
2. Context is auto-detected or manually selected:
   - **Strategy**: Attach to a specific position
   - **Routine**: Pre-market/preparation context
   - **Process**: Post-trade/reflection context
   - **Market**: General market conditions
3. AI parses prompt and captures reference state (if applicable)
4. Alert is created with appropriate type and evaluation mode

### View Filters

| Filter | Shows |
|--------|-------|
| **All** | All active alerts |
| **Routine** | Pre-market and preparation alerts |
| **Trading** | Position-attached alerts (price, AI, butterfly) |
| **Process** | Reflection, journaling, playbook alerts |
| **Triggered** | Recently triggered alerts needing attention |

### Alert Card Display

Each alert shows:
- Original prompt text (the trader's words)
- Current stage (Watching/Update/Warn/Accomplished)
- Context (Strategy label or workflow stage)
- Reference state summary (if applicable)
- Last evaluation time
- Actions menu (Edit, Disable, Delete)

For prompt alerts with stages:
```
┌────────────────────────────────────────────────────────────────────────┐
│ "Alert me if gamma starts eating into my profit zone"                  │
│                                                                        │
│ ○ Watching ──── ○ Update ──── ● Warn ──── ○ Accomplished               │
│                                                                        │
│ SPX 6000 BF  |  Gamma: 0.0012 → 0.0018 (+50%)  |  Confidence: 72%     │
│ "Gamma has increased significantly as spot approached strike"          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Integration Points

### Routine Drawer (Left)
- Routine alerts surface in the drawer
- Checklist items can generate alerts
- "Am I ready?" validation before trading

### Process Drawer (Right)
- Process alerts trigger after trade events
- Journal prompts appear contextually
- Playbook update reminders

### Risk Graph Panel
- Trading alerts visualized on chart
- Quick alert creation from price levels
- Strategy-attached alert status

### Trade Log
- Trade close events trigger process alerts
- Win/loss patterns feed retrospective alerts
- Alert history linked to trades

### ProcessBar
- Current phase affects alert context
- Routine/Process phases highlight relevant alerts
- Action phase shows active trading alerts

---

## Implementation Phases

### Phase 1: Foundation (Current)
- [x] Alert service API (Journal service)
- [x] Alert evaluation engine (Copilot service)
- [x] Prompt parser and evaluator
- [x] SSE real-time updates
- [ ] Alert Manager drawer UI (needs revision)

### Phase 2: Prompt-First Creation
- [ ] Integrate PromptAlertCreator as primary flow
- [ ] Context detection (strategy vs workflow)
- [ ] Reference state capture UI
- [ ] Confidence threshold selection

### Phase 3: Workflow Alerts
- [ ] Routine alert types and triggers
- [ ] Process alert types and triggers
- [ ] Event-based evaluation (not just market data)
- [ ] Integration with Routine/Process drawers

### Phase 4: Retrospective Intelligence
- [ ] Pattern detection across trade history
- [ ] Rule adherence tracking
- [ ] Behavioral alerts
- [ ] Learning loop integration

---

## Design Principles

1. **Natural Language First**: The prompt is the interface. Types are implementation details.

2. **Workflow Awareness**: Alerts span the entire trading day, not just positions.

3. **Non-Intrusive**: Alerts inform, they don't interrupt. Stages communicate urgency.

4. **Reference-Anchored**: Prompt alerts compare against captured state, not absolute values.

5. **AI-Evaluated**: When rules aren't enough, AI understands intent.

6. **Process Reinforcement**: Alerts help build good habits, not just react to prices.

---

## Files

### Frontend
| File | Purpose |
|------|---------|
| `ui/src/components/AlertManager/index.tsx` | Main drawer component |
| `ui/src/components/AlertManager/AlertManager.css` | Drawer styling |
| `ui/src/components/AlertManager/AlertCard.tsx` | Alert display |
| `ui/src/components/AlertManager/AlertFilters.tsx` | View filters |
| `ui/src/components/AlertManager/PromptInput.tsx` | Creation input |
| `ui/src/components/PromptAlertCreator.tsx` | Full creation modal |
| `ui/src/contexts/AlertContext.tsx` | State management |
| `ui/src/services/alertService.ts` | API client |
| `ui/src/types/alerts.ts` | Type definitions |

### Backend
| File | Purpose |
|------|---------|
| `services/journal/intel/db_v2.py` | Alert persistence |
| `services/journal/intel/orchestrator.py` | API routes |
| `services/copilot/intel/alert_engine.py` | Evaluation engine |
| `services/copilot/intel/alert_evaluators.py` | Type evaluators |
| `services/copilot/intel/prompt_evaluator.py` | Prompt evaluation |
| `services/copilot/intel/prompt_parser.py` | Intent parsing |
| `services/copilot/intel/reference_state_capture.py` | State capture |
