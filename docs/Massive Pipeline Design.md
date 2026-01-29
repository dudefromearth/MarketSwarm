# MarketSwarm Massive Pipeline Design Document

## Abstract

The Massive Pipeline is the core data ingestion and modeling engine in MarketSwarm, responsible for transforming raw options chain snapshots and real-time WebSocket updates into authoritative, low-latency convexity models (heatmap, GEX, and derived strategies). By separating structural authority (chain snapshots) from value mutations (WebSocket), and using epoch isolation with incremental computation, the pipeline achieves deterministic correctness, sub-second updates, and antifragility under market volatility. This document provides a complete overview of the pipeline architecture, flow, components, Redis wiring, and operational characteristics.

## Executive Summary

The Massive Pipeline operates in four primary stages: Massive (ingestion), Staging (normalization and hydration), Calculate Strategy (incremental model computation), and Models (publication of bound views). Chain snapshots provide canonical geometry and initial values; WebSocket streams mutate values incrementally within fixed epochs. Periodic snapshotting and dirty-driven recomputation enable efficient diffs for downstream UI and orthogonal widgets. The design prioritizes native Redis workspaces, delayed serialization, and epoch isolation for resilience and performance in high-volume financial environments.
![](Screenshot%202026-01-03%20at%2010.27.24%E2%80%AFAM.png)
## Table of Contents

1. Pipeline Overview and Architecture  
2. Stage 1: Massive (Ingestion)  
3. Stage 2: Staging (Normalization and Hydration)  
4. Stage 3: Calculate Strategy (Incremental Computation)  
5. Stage 4: Models (Publication and Binding)  
6. Redis Wiring and Key Patterns  
7. Operational Characteristics and Antifragility  

## 1. Pipeline Overview and Architecture

The Massive Pipeline is a Redis-native, event-driven flow that owns the full lifecycle from raw provider data to published convexity models.

- **Core Invariant**: Chain snapshots are the sole authority for contract geometry (strikes, expirations, universe).
- **Epoch Isolation**: Fixed geometry windows enable deterministic incremental updates.
- **Incremental Principle**: Only dirtied elements recompute; full rebuilds rare (new epoch only).
- **Delayed Serialization**: JSON/diffs produced only at publication.
- **Four Stages**: Massive → Staging → Calculate Strategy → Models (as illustrated in diagram).
- **Primary Flow**: Chain snapshots trigger staging → epoch promotion → model baselines; WebSocket hydrates → dirty flags → incremental strategy calculation → diff publication.

## 2. Stage 1: Massive (Ingestion)

This stage handles raw data acquisition from the provider.

- **Chain Snapshots**: Periodic or event-driven fetches of full option chains per underlying (SPX, NDX).
  - Code example (chain_worker.py trigger):
    ```python
    await self._run_once()  # fetches, publishes raw, triggers normalizers
    ```
- **WebSocket Stream**: Continuous connection for real-time contract updates.
  - Code example (ws_worker.py message handling):
    ```python
    pipe.xadd(self.stream_key, {"ts": ts, "payload": msg})
    ```
- **Spot Prices**: Real-time underlying values for range calculations.
- **Outputs**: Raw snapshots to massive:chain:snapshot:* and stream to massive:ws:stream.
- **Triggers**: Completion events drive next fetches (immediate-after-previous with optional buffering).

## 3. Stage 2: Staging (Normalization and Hydration)

Staging transforms raw data into epoch-scoped substrates.

- **Chain Authority**: Snapshots define geometry → pane/tile creation and heatmap sizing.
  - Code example (normalizer promotion):
    ```python
    await normalize_chain_snapshot_for_heatmap(..., snapshot)
    ```
- **Hydration**: WebSocket messages update existing contracts (no invention).
  - Code example (ws_hydrator.py):
    ```python
    pipe.hset(contract_key, mapping=updated_fields)  # partial overwrite
    ```
- **Change Detection**: Geometry change → new epoch; value change → dirty flags.
- **Snapshotting**: Periodic "Snapshot" node captures current hydrated state for strategy calculation.
- **Outputs**: epoch:{id}:contract:* (HASH for partial updates); dirty flags.

## 4. Stage 3: Calculate Strategy (Incremental Computation)

Strategy calculation operates incrementally on dirtied elements.

- **Dirty-Driven**: Only affected tiles/strategies recompute.
  - Code example (heatmap builder dirty poll):
    ```python
    dirty_epochs = await self.redis.smembers(self.epoch_dirty_set)
    for epoch_id in dirty_epochs:
        await self._calculate_for_epoch(epoch_id)  # partial tiles only
    ```
- **Strategies**: Butterfly, Vertical, Single — computed from hydrated contracts.
- **Diff Generation**: Changes only (e.g., updated tile values).
- **Triggers**: Hydration updates or periodic snapshot.
- **Outputs**: Incremental diffs for publication.

## 5. Stage 4: Models (Publication and Binding)

Final models are bound views published for consumption.

- **Core Models**: Heatmap (central convexity surface), GEX (gamma exposure by DTE).
- **Derived**: Liquidity Intent maps, Market Mode, Dealer Gravity.
- **Binding**: Heatmap geometry drives GEX/DTE; orthogonal widgets project subsets.
  - Code example (publication):
    ```python
    await self.redis.set(f"massive:heatmap:model:{symbol}", json.dumps(model))
    ```
- **Orthogonal Views**: Strategy-specific heatmaps (Butterfly/Vertical/Single per underlying).
- **Delivery**: SSE for diffs → UI incremental updates.
- **Consumers**: Dashboard widgets, Vigil events, Vexy intel.

## 6. Redis Wiring and Key Patterns

Redis (market-redis) is the native workspace for the entire pipeline.

- **Raw Ingestion**: massive:chain:snapshot:{symbol}:{exp}:*, massive:ws:stream.
- **Epoch Substrates**: epoch:{id}:contract:{id} (HASH for partial WS updates).
- **Active/Tracking**: epoch:active (HASH), epoch:meta:{id}, epoch:dirty/clean (SETS).
- **Published Models**: massive:heatmap:model:{symbol}, massive:gex:model:{symbol}:calls/puts.
- **Analytics**: massive:{source}:analytics (HASH/ZSET for latencies, counts).
- **Hygiene**: TTLs on epoch-scoped keys (~300s).

## 7. Operational Characteristics and Antifragility

The pipeline is designed for resilience in extreme financial conditions.

- **Latency**: Sub-second model updates via incremental diffs.
- **Throughput**: Bounded compute (dirty only); scales with Redis.
- **Burst Handling**: Epoch isolation + dirty flags absorb high-volume WS.
- **Disconnects**: Dormancy forces fresh chain promotion.
- **Observability**: Analytics + epoch-inspect.sh for promotion rates, dirty durations.
- **Restart Resilience**: Workspace persists; orchestrator/supervisor recovers state.

This pipeline delivers authoritative, real-time convexity models with minimal fragility, aligning with MarketSwarm's antifragile principles.