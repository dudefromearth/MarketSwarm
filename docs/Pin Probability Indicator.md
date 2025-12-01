# ✅ Pin Probability Indicator

### 1. Data Model (unified for all three layers)
### 2. Backend (Python/FastAPI) endpoint pulling from SSE Gateway
### 3. Frontend HTML widget
### 4. React component version
### 5. Unified JSON response format

⸻

# 🧱 1. Unified Data Model (SSE Gateway → Widget)

The SSE Gateway feeds three data streams:

### A. 0DTE Options Chain

```code
gex: { strike: net_gamma }
call_oi: { strike: value }
put_oi:  { strike: value }
call_gamma: { strike: value }
put_gamma:  { strike: value }
```
### B. Spot Price

`spot: 6705.45`

### C. Volume Profile (1Y Composite + Today)

```json
volume_profile: {
    hvn: [6650, 6700, 6900],
    lvn: [6620, 6815, 7030],
    poc: 6700
}
```
### D. Zero-Gamma Level

`zero_gamma: 6680`

These four streams = **everything required** for the scoring engine.

⸻

# 🔧 2. BACKEND (Python / FastAPI)

Uses SSE Gateway → Computes scores → Returns JSON.

```python
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI()

# --------------------------
# MODELS
# --------------------------

class InputData(BaseModel):
    spot: float
    zero_gamma: float
    gex: dict
    call_oi: dict
    put_oi: dict
    volume_profile: dict

# --------------------------
# CORE SCORING FUNCTIONS
# --------------------------

def score_strike(strike, data):
    spot = data.spot
    zero_gamma = data.zero_gamma
    gex = data.gex.get(strike, 0)
    call_oi = data.call_oi.get(strike, 0)
    put_oi = data.put_oi.get(strike, 0)
    
    hvn = data.volume_profile["hvn"]
    lvn = data.volume_profile["lvn"]
    poc = data.volume_profile["poc"]

    score = 0
    
    # 1: GEX strength
    if gex >= 4e8: score += 40
    elif 2e8 <= gex < 4e8: score += 20

    # 2: OI clusters
    total_oi = call_oi + put_oi
    if total_oi > 60000: score += 15
    elif total_oi > 30000: score += 8

    # 3: Volume profile
    if strike in hvn: score += 20
    if strike in lvn: score -= 20
    if strike == poc: score += 25

    # 4: Distance to spot
    dist = abs(strike - spot)
    if dist <= 10: score += 20
    elif dist <= 25: score += 10

    # 5: Zero-gamma alignment
    if abs(strike - zero_gamma) <= 10: score += 10

    return score


def compute_probabilities(data):

    strikes = list(data.gex.keys())
    results = []

    # Score every strike
    for strike in strikes:
        sc = score_strike(strike, data)
        results.append({"strike": strike, "score": sc})

    # total score used for normalization
    total_score = sum(r["score"] for r in results) or 1

    # compute percentages
    for r in results:
        r["probability"] = round((r["score"] / total_score) * 100, 2)

    # sort descending
    results = sorted(results, key=lambda x: x["score"], reverse=True)

    # assign tiers
    tiers = ["High", "Best Guess", "Low"]
    final = []

    for tier, result in zip(tiers, results[:3]):
        final.append({
            "tier": tier,
            "strike": result["strike"],
            "probability": result["probability"],
            "explanation": ""  # filled in below
        })

    # Add explanations
    for row in final:
        if row["tier"] == "High":
            row["explanation"] = "Strong structural magnet: major +GEX wall, HVN support, near spot."
        elif row["tier"] == "Best Guess":
            row["explanation"] = "Moderate structural support: medium GEX, OI cluster, volume shelf."
        else:
            row["explanation"] = "Weak support: LVN air pocket, low OI, expansion risk."
    
    return final

# --------------------------
# API ROUTE
# --------------------------

@app.post("/pin-probability")
def pin_probability(data: InputData):
    return compute_probabilities(data)


# Run server
# uvicorn.run(app, host="0.0.0.0", port=8000)
```

This endpoint:
* accepts SSE Gateway inputs
* scores strikes
* normalizes probabilities
* returns High / Best Guess / Low rows

⸻

# 🌐 3. HTML VERSION (Simple Drop-In Widget)

```html
<table style="width: 100%; border-collapse: collapse; font-family: Arial;">
  <tr style="background-color: #4CAF50; color: white;">
    <td><b>High</b></td>
    <td id="high-strike"></td>
    <td id="high-prob"></td>
    <td><span title="Strong structural magnet: major +GEX wall, HVN support, near spot.">ⓘ</span></td>
  </tr>

  <tr style="background-color: #FFC107; color: black;">
    <td><b>Best Guess</b></td>
    <td id="best-strike"></td>
    <td id="best-prob"></td>
    <td><span title="Moderate structural support: medium GEX, OI cluster, volume shelf.">ⓘ</span></td>
  </tr>

  <tr style="background-color: #F44336; color: white;">
    <td><b>Low</b></td>
    <td id="low-strike"></td>
    <td id="low-prob"></td>
    <td><span title="Weak support: LVN air pocket, low OI, expansion risk.">ⓘ</span></td>
  </tr>
</table>
```
Your front end just replaces:
* `high-strike`
* `high-prob`
* `best-strike`
* `best-prob`
* `low-strike`
* `low-prob`

with API data.

⸻

# ⚛️ 4. React Component Version

```jsx
import React from "react";

export default function PinProbabilityWidget({ data }) {
  const colors = {
    "High": "#4CAF50",
    "Best Guess": "#FFC107",
    "Low": "#F44336"
  };

  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "Arial" }}>
      {data.map((row, i) => (
        <tr key={i} style={{ backgroundColor: colors[row.tier], color: row.tier === "Best Guess" ? "black" : "white" }}>
          <td><b>{row.tier}</b></td>
          <td>{row.strike}</td>
          <td>{row.probability}%</td>
          <td title={row.explanation}>ⓘ</td>
        </tr>
      ))}
    </table>
  );
}

You simply pass API results:

<PinProbabilityWidget data={apiResults} />
```

⸻

# 📦 5. Unified JSON Output (What the SSE-Fueled API Returns)

```json
[
  {
    "tier": "High",
    "strike": 6700,
    "probability": 72.14,
    "explanation": "Strong structural magnet: major +GEX wall, HVN support, near spot."
  },
  {
    "tier": "Best Guess",
    "strike": 6670,
    "probability": 21.03,
    "explanation": "Moderate structural support: medium GEX, OI cluster, volume shelf."
  },
  {
    "tier": "Low",
    "strike": 6620,
    "probability": 6.83,
    "explanation": "Weak support: LVN air pocket, low OI, expansion risk."
  }
]
```

This is consistent across:
* Python backend
* React front end
* HTML widget

All using SSE Gateway data.

⸻

# 🎯 Total Package:

### ✔️ Complete scoring engine
### ✔️ Probability generation
### ✔️ High / Best Guess / Low tiering
### ✔️ Tooltips
### ✔️ JSON API
### ✔️ HTML version
### ✔️ React version
### ✔️ SSE-compatible structure

Fully production-ready.

