# MarketSwarm Epoch Design Document

## Abstract

The Epoch is a foundational concept in the MarketSwarm system, specifically within the Massive service, designed to provide structural isolation for options contract data. By fixing the geometry (strikes, expirations, and contract universe) from chain snapshots while allowing real-time value mutations via WebSocket updates, Epochs enable deterministic, incremental model computation. This document details the Epoch lifecycle, tracking mechanisms, instrumentation, philosophical rationale, and operational importance, now augmented with concrete code examples from the codebase to illustrate each aspect in practice.

## Executive Summary

Epochs address the core challenge of combining authoritative structural data (from slow chain snapshots) with high-frequency value updates (from WebSocket streams) without introducing non-determinism or excessive recomputation. An Epoch begins when geometry changes or dormancy is detected and is superseded (effectively ended) by the next promotion. Redis-native structures track active epochs, metadata, and states, with instrumentation providing observability into promotions, dirtiness, and dormancy. Code examples demonstrate promotion logic, metadata handling, and dormancy enforcement. Philosophically, Epochs enforce "truth boundaries" for data integrity; practically, they deliver efficiency, correctness, and antifragility under market stress.

## Table of Contents

1. Epoch Lifecycle  
2. Epoch Tracking and Redis Structures  
3. Epoch Instrumentation and Observability  
4. Philosophical and Practical Rationale  
5. Importance in MarketSwarm Operations  

## 1. Epoch Lifecycle

The Epoch lifecycle ensures a clear separation between structural changes (rare, authoritative) and value updates (frequent, incremental). This isolation prevents model thrash and guarantees consistency.

- **Start Conditions**: An Epoch starts when the ChainWorker processes a snapshot and detects a geometry mismatch (via hash of sorted strikes/expirations/contracts) compared to the current active Epoch, or when WebSocket dormancy exceeds the threshold (default 5 seconds of silence).
  - Code example from `epoch_manager.py` (promotion on geometry change):
    ```python
    if current_geometry_hash != new_geometry_hash:
        new_epoch_id = self._generate_epoch_id(symbol)
        await self.redis.hset(self.active_epoch_key, symbol, new_epoch_id)
        # ... metadata init, timeline push
    ```
- **Ongoing State**: Within an active Epoch, geometry is fixed; WebSocket updates mutate values only (e.g., mid, bid/ask, size) on existing contracts.
- **End Conditions**: Epochs do not explicitly "end"—they are superseded when a new Epoch is promoted for the same underlying; the prior Epoch is added to the timeline and eventually pruned via TTL.
  - Code example (supersession implicit in active update above).
- **Forced Promotion**: Dormancy detection forces a new Epoch even if geometry identical, ensuring models recompute with potentially stale values refreshed.
  - Code example from dormancy check:
    ```python
    if dormant_count > self.dormant_threshold:
        await self.force_new_epoch(symbol)  # creates new even if geometry same
    ```
- **HARD INVARIANT**: No structural changes (add/remove contracts) within an Epoch—violations would break determinism.

## 2. Epoch Tracking and Redis Structures

Epochs are tracked natively in Redis (market-redis bus) for real-time queryability and persistence across restarts.

- **Active Mapping**: `epoch:active` (HASH: underlying symbol → current epoch_id) tracks the live Epoch per symbol.
  - Code example (lookup/promotion):
    ```python
    current_id = await self.redis.hget(self.active_epoch_key, symbol)
    ```
- **Metadata**: `epoch:meta:{epoch_id}` (HASH) stores created_ts, strike_count, dormant_count, forced_dirty flags, etc.
  - Code example (init on promotion):
    ```python
    await self.redis.hset(meta_key, mapping={
        "created_ts": int(time.time()),
        "strike_count": len(strikes),
        "dormant_count": 0,
    })
    ```
- **Recompute Flags**: `epoch:dirty` (SET of epoch_ids needing model recalc) and `epoch:clean` (SET for completed).
  - Code example (mark dirty):
    ```python
    await self.redis.sadd(self.epoch_dirty_set, epoch_id)
    ```
- **Historical Timeline**: `epoch:timeline:{symbol}` (LIST of epoch_ids in order) for debugging and potential rollback.
  - Code example:
    ```python
    await self.redis.rpush(timeline_key, epoch_id)
    ```
- **WS Activity Flag**: `epoch:{epoch_id}:had_ws_updates` (STRING 0/1) indicates if WS contributed values.
  - Code example (on first WS hydration):
    ```python
    await self.redis.set(f"epoch:{epoch_id}:had_ws_updates", "1")
    ```
- **Hygiene**: Most epoch-scoped keys have TTL ~300s; active/meta persist longer.

## 3. Epoch Instrumentation and Observability

Instrumentation provides visibility into Epoch health, promotion frequency, and failure modes.

- **Built-In Counters**: Dormant_count in meta; dirty/clean SET cardinalities.
  - Code example (dormancy incr):
    ```python
    await self.redis.hincrby(meta_key, "dormant_count", 1)
    ```
- **Analytics Integration**: Promotion events can incr custom counters in massive:chain:analytics (e.g., geometry_changes, forced_dormancy).
- **Tools**: `epoch-inspect.sh` script outputs table with age, dirty status, dormant/forced flags, WS activity, and model contract counts.
  - Example output line:
    ```
    SPX     SPX:1700000000:abc         45      no     0        no      yes 1245     842
    ```
- **Expected Outputs**: Promotion rates (normal <1/min, burst higher); dormancy triggers (disconnect detection); dirty durations (model lag).
- **Dashboards/Alerts**: Feed into Heartbeat Aggregator for high promotion rates or persistent dirty epochs.

## 4. Philosophical and Practical Rationale

Epochs embody a deliberate philosophical choice to enforce data truth boundaries in a chaotic real-time financial environment.

- **Philosophical**: Epochs separate "what exists" (authoritative geometry from chain) from "current state" (mutable values from WS), preventing invention and ensuring models reason over consistent universes.
- **Real-World Drivers**: Options markets have structural events (new expirations, strike additions) separate from price flow; mixing causes non-determinism.
  - Code example enforcing separation (WS hydrator skips unknown contracts):
    ```python
    if parsed_symbol not in current_epoch_contracts:
        pipe.incr("massive:ws:hydrate:geometry_miss")
        continue  # skip, no invention
    ```
- **Antifragility**: Under stress (WS disconnects, geometry bursts), Epochs force controlled transitions rather than silent degradation.
- **Efficiency**: Incremental computation within fixed geometry reduces CPU/memory in high-volume regimes.
- **Correctness**: No orphaned/missing contracts in models.

## 5. Importance in MarketSwarm Operations

Epochs are critical for reliability, performance, and auditability in production.

- **Operational Stability**: Buffers WS churn; dormancy forces freshness during disconnects.
  - Code example (dormancy force):
    ```python
    if had_ws_updates == "0" and time_since_last > threshold:
        await self.force_new_epoch(symbol)
    ```
- **Performance**: Enables sub-second heatmap/GEX updates via incremental diffs.
- **Debugging/Auditing**: Timeline and meta allow tracing why a model changed (geometry vs. value).
- **Resilience**: Survives provider issues—prior Epoch valid until new promotion.
- **Scalability**: Fixed universes per Epoch bound memory/compute.
- **Overall System Health**: High promotion frequency signals provider volatility or config issues; low dirty duration indicates efficient models.

This design, illustrated with code examples, ensures MarketSwarm delivers authoritative, real-time convexity insights with minimal fragility.