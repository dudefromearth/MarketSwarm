#!/usr/bin/env python3
"""
strike-flow-live.py — Real-time strike flow visualization dashboard.

Web-based dashboard showing:
- Live tick activity heatmap
- Directional pressure by strike
- GEX overlay
- Spot price tracking

Usage:
    ./strike-flow-live.py                  # Start on port 8050
    ./strike-flow-live.py --port 8080      # Custom port

Then open http://localhost:8050 in browser.
"""

import argparse
import asyncio
import json
from collections import defaultdict
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
import uvicorn
from redis.asyncio import Redis

SYMBOL = "I:SPX"
REDIS_URL = "redis://127.0.0.1:6380"
UPDATE_INTERVAL = 0.25  # seconds (4 Hz)

app = FastAPI()


async def get_redis():
    return Redis.from_url(REDIS_URL, decode_responses=True)


async def get_spot(r: Redis, symbol: str) -> float | None:
    raw = await r.get(f"massive:model:spot:{symbol}")
    if raw:
        return float(json.loads(raw).get("value"))
    return None


async def get_gex(r: Redis, symbol: str) -> dict:
    calls_raw = await r.get(f"massive:gex:model:{symbol}:calls")
    puts_raw = await r.get(f"massive:gex:model:{symbol}:puts")

    calls = json.loads(calls_raw) if calls_raw else {}
    puts = json.loads(puts_raw) if puts_raw else {}

    gex_by_strike = {}
    for exp, strikes in calls.get("expirations", {}).items():
        for strike, gex in strikes.items():
            gex_by_strike[int(strike)] = gex_by_strike.get(int(strike), 0) + gex
    for exp, strikes in puts.get("expirations", {}).items():
        for strike, gex in strikes.items():
            gex_by_strike[int(strike)] = gex_by_strike.get(int(strike), 0) - gex

    return gex_by_strike


async def get_strike_activity(r: Redis, symbol: str, window_sec: int = 60) -> dict:
    """Get aggregated strike activity over window."""
    now = datetime.now().timestamp()
    start_ts = now - window_sec
    start_id = f"{int(start_ts * 1000)}-0"

    results = await r.xrange(f"massive:ws:strike:stream:{symbol}", min=start_id)

    aggregated = defaultdict(lambda: {"ticks": 0, "bids": 0, "asks": 0, "calls": 0, "puts": 0})

    for entry_id, fields in results:
        data = json.loads(fields.get("data", "{}"))
        for strike_str, stats in data.items():
            strike = int(strike_str)
            aggregated[strike]["ticks"] += stats.get("ticks", 0)
            aggregated[strike]["bids"] += stats.get("bids", 0)
            aggregated[strike]["asks"] += stats.get("asks", 0)
            aggregated[strike]["calls"] += stats.get("calls", 0)
            aggregated[strike]["puts"] += stats.get("puts", 0)

    return dict(aggregated)


async def get_recent_history(r: Redis, symbol: str, window_sec: int = 300, bucket_sec: int = 10) -> dict:
    """Get time-bucketed history for heatmap."""
    now = datetime.now().timestamp()
    start_ts = now - window_sec
    start_id = f"{int(start_ts * 1000)}-0"

    results = await r.xrange(f"massive:ws:strike:stream:{symbol}", min=start_id)

    # Bucket by time
    buckets = defaultdict(lambda: defaultdict(lambda: {"ticks": 0, "pressure": 0}))

    for entry_id, fields in results:
        ts = float(fields.get("ts", 0))
        bucket_ts = int(ts // bucket_sec) * bucket_sec
        data = json.loads(fields.get("data", "{}"))

        for strike_str, stats in data.items():
            strike = int(strike_str)
            buckets[bucket_ts][strike]["ticks"] += stats.get("ticks", 0)
            buckets[bucket_ts][strike]["pressure"] += stats.get("bids", 0) - stats.get("asks", 0)

    return dict(buckets)


async def get_event_bucketed_history(r: Redis, symbol: str, ticks_per_bucket: int = 500, num_buckets: int = 60) -> list:
    """
    Get event-bucketed history — each bucket represents N ticks, not N seconds.
    Returns list of buckets, each with timestamp and strike activity.
    """
    # Get recent stream entries (enough to fill buckets)
    results = await r.xrevrange(
        f"massive:ws:strike:stream:{symbol}",
        count=num_buckets * 10  # Oversample to ensure we have enough
    )
    results.reverse()  # Oldest first

    if not results:
        return []

    buckets = []
    current_bucket = {"ts": None, "strikes": defaultdict(lambda: {"ticks": 0, "pressure": 0}), "total_ticks": 0}

    for entry_id, fields in results:
        ts = float(fields.get("ts", 0))
        data = json.loads(fields.get("data", "{}"))

        if current_bucket["ts"] is None:
            current_bucket["ts"] = ts

        for strike_str, stats in data.items():
            strike = int(strike_str)
            ticks = stats.get("ticks", 0)
            current_bucket["strikes"][strike]["ticks"] += ticks
            current_bucket["strikes"][strike]["pressure"] += stats.get("bids", 0) - stats.get("asks", 0)
            current_bucket["total_ticks"] += ticks

        # Check if bucket is full
        if current_bucket["total_ticks"] >= ticks_per_bucket:
            buckets.append({
                "ts": current_bucket["ts"],
                "end_ts": ts,
                "strikes": dict(current_bucket["strikes"]),
                "total_ticks": current_bucket["total_ticks"],
            })
            current_bucket = {"ts": None, "strikes": defaultdict(lambda: {"ticks": 0, "pressure": 0}), "total_ticks": 0}

            if len(buckets) >= num_buckets:
                break

    # Add partial bucket if it has data
    if current_bucket["total_ticks"] > 0:
        buckets.append({
            "ts": current_bucket["ts"],
            "end_ts": ts,
            "strikes": dict(current_bucket["strikes"]),
            "total_ticks": current_bucket["total_ticks"],
        })

    return buckets


async def stream_data(symbol: str) -> AsyncGenerator[str, None]:
    """SSE stream of live data."""
    r = await get_redis()

    try:
        while True:
            spot = await get_spot(r, symbol)
            gex = await get_gex(r, symbol)
            activity = await get_strike_activity(r, symbol, window_sec=15)
            event_history = await get_event_bucketed_history(r, symbol, ticks_per_bucket=300, num_buckets=50)

            # Build payload
            payload = {
                "ts": datetime.now().isoformat(),
                "spot": spot,
                "gex": gex,
                "activity": activity,
                "event_history": event_history,
            }

            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(UPDATE_INTERVAL)

    finally:
        await r.aclose()


@app.get("/stream/{symbol}")
async def stream_endpoint(symbol: str):
    return StreamingResponse(
        stream_data(symbol),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Strike Flow Live</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0a0a0a;
            color: #fff;
            font-family: 'Consolas', 'Monaco', monospace;
            overflow: hidden;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 20px;
            background: #1a1a1a;
            border-bottom: 1px solid #333;
        }
        .header h1 { font-size: 18px; color: #0ff; }
        .header .spot { font-size: 24px; color: #ff0; }
        .header .status { font-size: 12px; color: #0f0; }
        .container {
            display: grid;
            grid-template-columns: 200px 1fr 200px 120px;
            grid-template-rows: 1fr;
            gap: 5px;
            padding: 5px;
            height: calc(100vh - 50px);
        }
        .panel {
            background: #111;
            border: 1px solid #333;
            border-radius: 4px;
            overflow: hidden;
        }
        .panel-title {
            background: #222;
            padding: 5px 10px;
            font-size: 12px;
            color: #888;
            border-bottom: 1px solid #333;
        }
        #gex-chart { }
        #heatmap { }
        #pressure-chart { }
        #arrows-chart { }
        .chart { width: 100%; height: calc(100% - 25px); }
    </style>
</head>
<body>
    <div class="header">
        <h1>Strike Flow Live - I:SPX</h1>
        <div class="spot">Spot: <span id="spot-value">--</span></div>
        <div class="status" id="status">Connecting...</div>
    </div>
    <div class="container">
        <div class="panel" id="gex-chart">
            <div class="panel-title">Gamma Exposure</div>
            <div id="gex" class="chart"></div>
        </div>
        <div class="panel" id="heatmap">
            <div class="panel-title">Tick Activity + Flow Trail (300 ticks/column)</div>
            <div id="heat" class="chart"></div>
        </div>
        <div class="panel" id="pressure-chart">
            <div class="panel-title">Call/Put Flow (15s)</div>
            <div id="pressure" class="chart"></div>
        </div>
        <div class="panel" id="arrows-chart">
            <div class="panel-title">Net Flow</div>
            <div id="arrows" class="chart"></div>
        </div>
    </div>

    <script>
        const SYMBOL = 'I:SPX';
        const STRIKE_RANGE = 75;
        let spot = null;
        let lastUpdate = null;

        const layout = {
            paper_bgcolor: '#111',
            plot_bgcolor: '#111',
            font: { color: '#888', size: 10 },
            margin: { l: 50, r: 20, t: 10, b: 30 },
            xaxis: { gridcolor: '#222', zerolinecolor: '#444' },
            yaxis: { gridcolor: '#222', zerolinecolor: '#444' },
        };

        // Initialize charts
        Plotly.newPlot('gex', [], {...layout, yaxis: {gridcolor: '#222'}});
        Plotly.newPlot('heat', [], {...layout, yaxis: {gridcolor: '#222'}});
        Plotly.newPlot('pressure', [], {...layout, yaxis: {gridcolor: '#222'}});
        Plotly.newPlot('arrows', [], {...layout, yaxis: {gridcolor: '#222'}});

        function updateCharts(data) {
            spot = data.spot;
            document.getElementById('spot-value').textContent = spot ? spot.toFixed(2) : '--';
            document.getElementById('status').textContent = `Updated: ${new Date().toLocaleTimeString()}`;

            if (!spot) return;

            // Filter strikes around spot (descending: high strikes at top)
            const minStrike = Math.floor((spot - STRIKE_RANGE) / 5) * 5;
            const maxStrike = Math.ceil((spot + STRIKE_RANGE) / 5) * 5;
            const strikes = [];
            for (let s = minStrike; s <= maxStrike; s += 5) strikes.push(s);
            strikes.reverse();  // Now [maxStrike, ..., minStrike] - high at top

            // GEX chart
            const gexValues = strikes.map(s => data.gex[s] || 0);
            const gexColors = gexValues.map(v => v > 0 ? '#00aa00' : '#aa0000');

            Plotly.react('gex', [{
                type: 'bar',
                x: gexValues,
                y: strikes.map(String),
                orientation: 'h',
                marker: { color: gexColors },
            }], {
                ...layout,
                yaxis: { ...layout.yaxis, type: 'category', categoryorder: 'array', categoryarray: strikes.map(String), autorange: 'reversed' },
                shapes: [{
                    type: 'line',
                    x0: 0, x1: 0,
                    y0: -0.5, y1: strikes.length - 0.5,
                    line: { color: '#444', width: 1 }
                }, {
                    type: 'line',
                    x0: Math.min(...gexValues) * 1.1, x1: Math.max(...gexValues) * 1.1,
                    y0: strikes.indexOf(Math.round(spot / 5) * 5),
                    y1: strikes.indexOf(Math.round(spot / 5) * 5),
                    line: { color: '#0ff', width: 2, dash: 'dash' }
                }]
            });

            // Pressure chart - calls vs puts (positive = call heavy = bullish)
            const pressureValues = strikes.map(s => {
                const act = data.activity[s];
                return act ? (act.calls - act.puts) : 0;
            });
            const pressureColors = pressureValues.map(v => v > 0 ? '#00aa00' : '#aa0000');

            Plotly.react('pressure', [{
                type: 'bar',
                x: pressureValues,
                y: strikes.map(String),
                orientation: 'h',
                marker: { color: pressureColors },
            }], {
                ...layout,
                yaxis: { ...layout.yaxis, type: 'category', categoryorder: 'array', categoryarray: strikes.map(String), autorange: 'reversed' },
                shapes: [{
                    type: 'line',
                    x0: 0, x1: 0,
                    y0: -0.5, y1: strikes.length - 0.5,
                    line: { color: '#444', width: 1 }
                }, {
                    type: 'line',
                    x0: Math.min(...pressureValues) * 1.1 || -1,
                    x1: Math.max(...pressureValues) * 1.1 || 1,
                    y0: strikes.indexOf(Math.round(spot / 5) * 5),
                    y1: strikes.indexOf(Math.round(spot / 5) * 5),
                    line: { color: '#0ff', width: 2, dash: 'dash' }
                }]
            });

            // Single aggregate arrow - total directional pressure
            const totalPressure = pressureValues.reduce((sum, v) => sum + v, 0);
            const isUp = totalPressure > 0;
            const magnitude = Math.abs(totalPressure);

            // Scale arrow: length 0.1 to 0.9, width 5 to 30
            const maxExpected = 2000;  // Adjust based on typical values
            const normalized = Math.min(magnitude / maxExpected, 1);
            const arrowLength = 0.1 + normalized * 0.8;
            const arrowWidth = 5 + normalized * 25;

            const arrowColor = isUp ? '#00ff00' : '#ff0000';
            const yStart = isUp ? 0.5 - arrowLength/2 : 0.5 + arrowLength/2;
            const yEnd = isUp ? 0.5 + arrowLength/2 : 0.5 - arrowLength/2;

            Plotly.react('arrows', [], {
                ...layout,
                showlegend: false,
                xaxis: { range: [0, 1], showticklabels: false, showgrid: false, zeroline: false, visible: false },
                yaxis: { range: [0, 1], showticklabels: false, showgrid: false, zeroline: false, visible: false },
                annotations: [{
                    x: 0.5,
                    y: yEnd,
                    ax: 0.5,
                    ay: yStart,
                    xref: 'x',
                    yref: 'y',
                    axref: 'x',
                    ayref: 'y',
                    showarrow: true,
                    arrowhead: 2,
                    arrowsize: 2,
                    arrowwidth: arrowWidth,
                    arrowcolor: arrowColor,
                }, {
                    x: 0.5,
                    y: 0.05,
                    text: `${isUp ? '+' : ''}${totalPressure}`,
                    showarrow: false,
                    font: { color: arrowColor, size: 16 },
                }]
            });

            // Heatmap - event-bucketed (each column = N ticks)
            const eventHistory = data.event_history || [];

            if (eventHistory.length > 0) {
                const z = strikes.map(strike =>
                    eventHistory.map(bucket => {
                        const strikeData = bucket.strikes[strike];
                        return strikeData ? strikeData.ticks : 0;
                    })
                );

                // Labels show bucket number and tick count
                const timeLabels = eventHistory.map((bucket, idx) => {
                    const d = new Date(bucket.ts * 1000);
                    const time = d.toLocaleTimeString('en-US', { hour12: false, minute: '2-digit', second: '2-digit' });
                    return `${time}`;
                });

                const spotIdx = strikes.indexOf(Math.round(spot / 5) * 5);

                // Calculate flow centroid (weighted average strike) for each event bucket
                const flowTrail = eventHistory.map((bucket, tIdx) => {
                    let totalTicks = 0;
                    let weightedSum = 0;
                    strikes.forEach((strike, sIdx) => {
                        const ticks = z[sIdx][tIdx] || 0;
                        totalTicks += ticks;
                        weightedSum += strike * ticks;
                    });
                    return totalTicks > 0 ? weightedSum / totalTicks : null;
                });

                // Convert flow trail to y-indices for plotting
                const flowTrailIdx = flowTrail.map(strike => {
                    if (strike === null) return null;
                    const closest = strikes.reduce((prev, curr) =>
                        Math.abs(curr - strike) < Math.abs(prev - strike) ? curr : prev
                    );
                    return strikes.indexOf(closest);
                });

                Plotly.react('heat', [{
                    type: 'heatmap',
                    z: z,
                    x: timeLabels,
                    y: strikes.map(String),
                    colorscale: [
                        [0, '#000'],
                        [0.1, '#1a0a2e'],
                        [0.3, '#5c2d91'],
                        [0.5, '#b5338a'],
                        [0.7, '#f5736a'],
                        [1, '#ffd700']
                    ],
                    showscale: true,
                    colorbar: { tickfont: { color: '#888' } },
                    hovertemplate: 'Strike: %{y}<br>Time: %{x}<br>Ticks: %{z}<extra></extra>',
                }, {
                    // Flow trail - shows center of mass of activity
                    type: 'scatter',
                    x: timeLabels,
                    y: flowTrail.map(s => s ? String(Math.round(s / 5) * 5) : null),
                    mode: 'lines+markers',
                    line: { color: '#0f0', width: 3 },
                    marker: { color: '#0f0', size: 6 },
                    name: 'Flow Trail',
                    connectgaps: false,
                }], {
                    ...layout,
                    yaxis: { ...layout.yaxis, type: 'category', categoryorder: 'array', categoryarray: strikes.map(String), autorange: 'reversed' },
                    shapes: [{
                        type: 'line',
                        x0: -0.5, x1: eventHistory.length - 0.5,
                        y0: spotIdx, y1: spotIdx,
                        line: { color: '#0ff', width: 2, dash: 'dash' }
                    }],
                    annotations: [{
                        x: eventHistory.length - 1,
                        y: spotIdx,
                        text: ` Spot ${spot.toFixed(0)}`,
                        showarrow: false,
                        font: { color: '#0ff', size: 10 },
                        xanchor: 'left'
                    }]
                });
            }
        }

        // Connect to SSE stream
        const evtSource = new EventSource(`/stream/${SYMBOL}`);

        evtSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            updateCharts(data);
        };

        evtSource.onerror = () => {
            document.getElementById('status').textContent = 'Connection lost - reconnecting...';
            document.getElementById('status').style.color = '#f00';
        };

        evtSource.onopen = () => {
            document.getElementById('status').style.color = '#0f0';
        };
    </script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Strike Flow Live Dashboard")
    parser.add_argument("--port", type=int, default=8050, help="Port to run on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()

    print(f"Starting Strike Flow Live on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
