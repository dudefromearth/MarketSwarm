#!/usr/bin/env python3
# services/massive/intel/chain_worker.py

from __future__ import annotations

import asyncio
import json
import math
import os
import time
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional, Tuple

from redis.asyncio import Redis
from massive import RESTClient  # Massive.com Python client

import logutil  # services/massive/logutil.py


def _round_to_nearest_5(x: float) -> int:
    return int(round(x / 5.0)) * 5


def _iso_utc_now() -> str:
    # Match previous snapshot keys: seconds, with timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso_date(s: str) -> date:
    return datetime.fromisoformat(s).date()


def _yyyymmdd_from_iso(exp_iso: str) -> str:
    """
    Convert 'YYYY-MM-DD' -> 'YYYYMMDD'.
    """
    return exp_iso.replace("-", "")


def _build_ws_channels(
    underlying: str,
    expiry_iso: str,
    low_strike: float,
    high_strike: float,
    strike_step: int,
) -> List[str]:
    """
    Build Massive T.O channels for all calls + puts between low_strike and
    high_strike (inclusive), at `strike_step` spacing.

    Example channel:
      T.O:SPXW251209C06850000
    """
    if strike_step <= 0:
        raise ValueError("strike_step must be positive")

    expiry_yyyymmdd = _yyyymmdd_from_iso(expiry_iso)      # '2025-12-09' -> '20251209'
    expiry_yymmdd = expiry_yyyymmdd[2:]                   # '20251209' -> '251209'
    underlying_prefix = f"{underlying}W"                  # 'SPX' -> 'SPXW'

    # Normalize bounds to the strike grid
    low = math.floor(low_strike / strike_step) * strike_step
    high = math.ceil(high_strike / strike_step) * strike_step

    channels: List[str] = []
    k = float(low)
    high_f = float(high)

    # Simple loop over the strike grid
    while k <= high_f + 1e-9:  # small epsilon for float math
        # Massive/SPX style: strike * 1000, zero-padded to 8 digits
        value = int(round(k * 1000))
        strike_part = f"{value:08d}"

        for right in ("C", "P"):
            contract = f"{underlying_prefix}{expiry_yymmdd}{right}{strike_part}"
            channels.append(f"T.O:{contract}")

        k += float(strike_step)

    return channels


class ChainWorker:
    """
    Periodic full-chain snapshot worker.

    Responsibilities:
      - Read latest SPX & VIX spot from Market-Redis
      - Compute an effective ±range using VIX-based expected move
        (falling back to fixed ±points if VIX is unavailable)
      - For the next N expirations:
          * Fetch options from Massive within [ATM - range, ATM + range]
          * Store a JSON snapshot:
              CHAIN:{U}:EXP:{YYYY-MM-DD}:snap:{ts}
          * Update latest pointer:
              CHAIN:{U}:EXP:{YYYY-MM-DD}:latest -> snap key
      - Derive WebSocket trade channels for each expiration and publish
        a params string into:
              massive:ws:params:{YYYYMMDD}
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.service_name = config.get("service_name", "massive")

        # Core symbol wiring
        self.api_symbol: str = os.getenv("MASSIVE_SYMBOL", "I:SPX").strip()
        if self.api_symbol.startswith("I:"):
            self.underlying: str = self.api_symbol[2:]
        else:
            self.underlying = self.api_symbol

        # Redis
        self.market_redis_url: str = os.getenv(
            "MARKET_REDIS_URL", "redis://127.0.0.1:6380"
        )
        self._redis_market: Optional[Redis] = None

        # Cadence / geometry config
        self.interval_sec: int = int(os.getenv("MASSIVE_CHAIN_INTERVAL_SEC", "60"))

        # Fallback ±points around ATM if EM cannot be computed
        self.fallback_range_points: int = int(
            os.getenv("MASSIVE_CHAIN_STRIKE_RANGE", "150")
        )

        # How many expirations to load each cycle
        self.num_expirations: int = int(
            os.getenv("MASSIVE_CHAIN_NUM_EXPIRATIONS", "5")
        )

        # Massive API limits
        self.max_chain_limit: int = 250  # hard cap per API docs

        # Snapshot TTL
        self.snapshot_ttl_sec: int = int(
            os.getenv("MASSIVE_CHAIN_SNAPSHOT_TTL_SEC", "600")
        )

        # Trail config (reserved for future; not used right now)
        self.trail_window_sec: int = int(
            os.getenv("MASSIVE_CHAIN_TRAIL_WINDOW_SEC", "86400")
        )
        self.trail_ttl_sec: int = int(
            os.getenv("MASSIVE_CHAIN_TRAIL_TTL_SEC", "172800")
        )

        # Expected move parameters
        self.em_days: int = int(os.getenv("MASSIVE_CHAIN_EM_DAYS", "1"))
        self.em_mult: float = float(os.getenv("MASSIVE_CHAIN_EM_MULT", "2.0"))

        # Inclusive vs strict strike filter
        self.use_strict_gt_lt: bool = (
            os.getenv("MASSIVE_CHAIN_STRICT_GT_LT", "false").lower() == "true"
        )

        # WS strike step (used to build trade channels)
        self.ws_strike_step: int = int(os.getenv("MASSIVE_WS_STRIKE_STEP", "5"))

        # Massive API client
        api_key = os.getenv("MASSIVE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("MASSIVE_API_KEY not set for ChainWorker")

        self.client = RESTClient(api_key)

        self.debug_enabled: bool = (
            os.getenv("DEBUG_MASSIVE", "false").lower() == "true"
        )

        logutil.log(
            self.service_name,
            "INFO",
            "🔧",
            (
                "ChainWorker init: "
                f"api_symbol={self.api_symbol}, U={self.underlying}, "
                f"interval={self.interval_sec}s, "
                f"fallback_range=±{self.fallback_range_points}, "
                f"num_expirations={self.num_expirations}, "
                f"max_limit={self.max_chain_limit}, "
                f"snapshot_ttl={self.snapshot_ttl_sec}s, "
                f"trail_window={self.trail_window_sec}s, "
                f"trail_ttl={self.trail_ttl_sec}s, "
                f"EM_days={self.em_days}, EM_mult={self.em_mult}, "
                f"ws_strike_step={self.ws_strike_step}"
            ),
        )

    # ------------------------------------------------------------
    # Redis helper
    # ------------------------------------------------------------
    async def _market_redis(self) -> Redis:
        if self._redis_market is None:
            self._redis_market = Redis.from_url(
                self.market_redis_url, decode_responses=True
            )
        return self._redis_market

    # ------------------------------------------------------------
    # Spot helpers
    # ------------------------------------------------------------
    async def _load_spot_value(self, symbol: str) -> Optional[float]:
        """
        Load numeric spot from massive:model:spot:{symbol} in Market-Redis.
        """
        r = await self._market_redis()
        key = f"massive:model:spot:{symbol}"
        raw = await r.get(key)
        if not raw:
            logutil.log(
                self.service_name,
                "WARN",
                "⚠️",
                f"spot key missing: {key}",
            )
            return None

        try:
            data = json.loads(raw)
        except Exception as e:
            logutil.log(
                self.service_name,
                "ERROR",
                "💥",
                f"invalid spot JSON at {key}: {e}",
            )
            return None

        val = data.get("value")
        if val is None:
            logutil.log(
                self.service_name,
                "WARN",
                "⚠️",
                f"spot 'value' missing in {key}",
            )
            return None

        try:
            return float(val)
        except (TypeError, ValueError):
            logutil.log(
                self.service_name,
                "WARN",
                "⚠️",
                f"spot value not numeric in {key}: {val!r}",
            )
            return None

    async def _load_spx_and_vix_spot(self) -> Tuple[Optional[float], Optional[float]]:
        spx = await self._load_spot_value(self.underlying)  # "SPX"
        vix = await self._load_spot_value("VIX")
        return spx, vix

    # ------------------------------------------------------------
    # Expected move geometry
    # ------------------------------------------------------------
    def _compute_range_from_expected_move(
        self,
        spot_spx: float,
        spot_vix: Optional[float],
    ) -> int:
        """
        Compute ±range in points using a simple VIX-based expected move:

            EM_raw ≈ S * (VIX / 100) * sqrt(H / 252)
            EM_pts = EM_mult * EM_raw

        Returns an integer number of points (rounded) or falls back
        to self.fallback_range_points if VIX is unavailable or invalid.
        """
        if spot_vix is None or spot_vix <= 0:
            # No usable VIX → fallback
            logutil.log(
                self.service_name,
                "INFO",
                "📐",
                (
                    f"VIX spot unavailable/invalid; "
                    f"using fallback ±{self.fallback_range_points} pts for {self.underlying}"
                ),
            )
            return self.fallback_range_points

        # EM baseline for H days
        em_raw = spot_spx * (spot_vix / 100.0) * math.sqrt(
            float(self.em_days) / 252.0
        )
        em_pts = self.em_mult * em_raw

        # Round to nearest whole point
        effective = int(round(em_pts)) if em_pts > 0 else self.fallback_range_points

        logutil.log(
            self.service_name,
            "INFO",
            "📐",
            (
                f"Using expected-move range from VIX for {self.underlying}: "
                f"±{effective:.1f} pts (H={self.em_days}, mult={self.em_mult})"
            ),
        )
        return effective

    # ------------------------------------------------------------
    # Massive helpers
    # ------------------------------------------------------------
    def _list_all_expirations(self) -> List[str]:
        """
        Pull a broad chain slice (limit=max_chain_limit) and extract
        all distinct expiration dates for this symbol.
        """
        exps = set()
        try:
            for opt in self.client.list_snapshot_options_chain(
                self.api_symbol, params={"limit": self.max_chain_limit}
            ):
                exp = getattr(getattr(opt, "details", None), "expiration_date", None)
                if exp:
                    exps.add(exp)
        except Exception as e:
            logutil.log(
                self.service_name,
                "ERROR",
                "💥",
                f"failed to list expirations for {self.api_symbol}: {e}",
            )
            return []

        out = sorted(exps)
        logutil.log(
            self.service_name,
            "INFO",
            "ℹ️",
            f"ChainWorker: {len(out)} expirations available for {self.api_symbol}",
        )
        return out

    def _build_strike_filters(self, lower: float, upper: float) -> Dict[str, Any]:
        if self.use_strict_gt_lt:
            return {
                "strike_price.gt": lower,
                "strike_price.lt": upper,
            }
        else:
            return {
                "strike_price.gte": lower,
                "strike_price.lte": upper,
            }

    def _fetch_contracts_for_expiration(
        self,
        expiration: str,
        atm_strike: int,
        strike_range_points: int,
    ) -> Tuple[List[Dict[str, Any]], Optional[float], Optional[float]]:
        """
        Fetch contracts for [ATM - range, ATM + range] at a specific expiration.

        Returns:
          (contracts, strike_min, strike_max)
        """
        lower = atm_strike - strike_range_points
        upper = atm_strike + strike_range_points

        params: Dict[str, Any] = {
            "expiration_date": expiration,
            "order": "asc",
            "sort": "strike_price",
            "limit": self.max_chain_limit,
        }
        params.update(self._build_strike_filters(lower, upper))

        logutil.log(
            self.service_name,
            "INFO",
            "🔎",
            (
                f"Fetching {self.api_symbol} exp={expiration}, "
                f"ATM={atm_strike}, range=({lower}–{upper}), strict={self.use_strict_gt_lt}"
            ),
        )

        contracts: List[Dict[str, Any]] = []
        strike_min: Optional[float] = None
        strike_max: Optional[float] = None

        try:
            for opt in self.client.list_snapshot_options_chain(
                self.api_symbol, params=params
            ):
                # Convert Massive object to dict
                raw = json.loads(json.dumps(opt, default=lambda o: o.__dict__))

                # Extract strike from details
                details = raw.get("details") or {}
                strike = details.get("strike_price")

                if strike is not None:
                    try:
                        sf = float(strike)
                        if strike_min is None or sf < strike_min:
                            strike_min = sf
                        if strike_max is None or sf > strike_max:
                            strike_max = sf
                    except (TypeError, ValueError):
                        # Ignore bad strike and still keep contract
                        pass

                contracts.append(raw)

        except Exception as e:
            logutil.log(
                self.service_name,
                "ERROR",
                "💥",
                f"chain fetch failed for {self.api_symbol} exp={expiration}: {e}",
            )
            return [], None, None

        logutil.log(
            self.service_name,
            "INFO",
            "ℹ️",
            f"{self.api_symbol} {expiration} → {len(contracts)} contracts (filtered)",
        )
        return contracts, strike_min, strike_max

    # ------------------------------------------------------------
    # Snapshot writer
    # ------------------------------------------------------------
    async def _write_snapshot(
        self,
        exp: str,
        dte: int,
        spot_spx: float,
        strike_range_points: int,
        strike_min: Optional[float],
        strike_max: Optional[float],
        contracts: List[Dict[str, Any]],
    ) -> None:
        """
        Write:

          CHAIN:{U}:EXP:{exp}:snap:{ts}   → full JSON snapshot
          CHAIN:{U}:EXP:{exp}:latest      → pointer to snapshot key

        And publish WS channel params for this expiration:

          massive:ws:params:{YYYYMMDD}    → comma-joined channels
        """
        r = await self._market_redis()

        ts_iso = _iso_utc_now()
        snap_key = f"CHAIN:{self.underlying}:EXP:{exp}:snap:{ts_iso}"
        latest_key = f"CHAIN:{self.underlying}:EXP:{exp}:latest"

        # --- WS channels / params -----------------------------------------
        ws_channels: List[str] = []
        ws_params_key: Optional[str] = None

        if strike_min is not None and strike_max is not None:
            try:
                ws_channels = _build_ws_channels(
                    underlying=self.underlying,
                    expiry_iso=exp,
                    low_strike=strike_min,
                    high_strike=strike_max,
                    strike_step=self.ws_strike_step,
                )
                expiry_yyyymmdd = _yyyymmdd_from_iso(exp)
                ws_params_key = f"massive:ws:params:{expiry_yyyymmdd}"

                # Comma-joined string for WsWorker
                await r.set(ws_params_key, ",".join(ws_channels))

                logutil.log(
                    self.service_name,
                    "INFO",
                    "📺",
                    (
                        f"WS params updated for {self.underlying} exp={exp} "
                        f"({ws_params_key}, {len(ws_channels)} channels)"
                    ),
                )
            except Exception as e:
                logutil.log(
                    self.service_name,
                    "ERROR",
                    "💥",
                    f"Failed to build WS channels for exp={exp}: {e}",
                )

        # --- Snapshot model -----------------------------------------------
        model: Dict[str, Any] = {
            "symbol": self.underlying,
            "api_symbol": self.api_symbol,
            "exp": exp,
            "dte": dte,
            "ts": ts_iso,
            "source": "massive/snapshot/options",
            "spot": spot_spx,
            "spot_source": f"massive:model:spot:{self.underlying}",
            "strike_min": strike_min,
            "strike_max": strike_max,
            "strike_range_points": strike_range_points,
            "count": len(contracts),
            "contracts": contracts,

            # WS metadata for downstream consumers
            "ws_params_key": ws_params_key,
            "ws_channels": ws_channels,
            "ws_channels_count": len(ws_channels),
            "ws_strike_step": self.ws_strike_step,
        }

        payload = json.dumps(model)

        # Store snapshot with TTL
        await r.set(snap_key, payload, ex=self.snapshot_ttl_sec)
        # Update pointer to latest
        await r.set(latest_key, snap_key, ex=self.snapshot_ttl_sec)

        logutil.log(
            self.service_name,
            "INFO",
            "💾",
            (
                f"CHAIN updated {self.underlying} exp={exp} "
                f"(latest={latest_key}, snap={snap_key})"
            ),
        )

    # ------------------------------------------------------------
    # Single cycle
    # ------------------------------------------------------------
    async def _run_once(self) -> None:
        """
        One periodic cycle:
          - Load SPX + VIX spot
          - Compute range from expected move (with fallback)
          - List expirations
          - Fetch & store for the next N expirations
        """
        # 1) Spot
        spot_spx, spot_vix = await self._load_spx_and_vix_spot()
        if spot_spx is None:
            logutil.log(
                self.service_name,
                "WARN",
                "⚠️",
                "ChainWorker: SPX spot unavailable; skipping cycle",
            )
            return

        # 2) Range from expected move (or fallback)
        strike_range_points = self._compute_range_from_expected_move(
            spot_spx=spot_spx,
            spot_vix=spot_vix,
        )

        # 3) Expirations
        exps = await asyncio.to_thread(self._list_all_expirations)
        if not exps:
            return

        target_exps = exps[: self.num_expirations]

        today = datetime.now(timezone.utc).date()

        # 4) For each expiration, fetch + store snapshot
        for exp in target_exps:
            try:
                atm = _round_to_nearest_5(spot_spx)
                contracts, strike_min, strike_max = await asyncio.to_thread(
                    self._fetch_contracts_for_expiration,
                    exp,
                    atm,
                    strike_range_points,
                )

                if not contracts:
                    continue

                # DTE in calendar days
                try:
                    exp_date = _parse_iso_date(exp)
                    dte = (exp_date - today).days
                except Exception:
                    dte = 0

                await self._write_snapshot(
                    exp=exp,
                    dte=dte,
                    spot_spx=spot_spx,
                    strike_range_points=strike_range_points,
                    strike_min=strike_min,
                    strike_max=strike_max,
                    contracts=contracts,
                )
            except Exception as e:
                logutil.log(
                    self.service_name,
                    "ERROR",
                    "💥",
                    f"ChainWorker: error while processing exp={exp}: {e}",
                )

    # ------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------
    async def run(self, stop_event: asyncio.Event) -> None:
        """
        Long-running async loop. Respects stop_event and interval_sec.
        """
        logutil.log(
            self.service_name,
            "INFO",
            "🚀",
            f"ChainWorker starting for {self.api_symbol} (interval={self.interval_sec}s)",
        )

        try:
            while not stop_event.is_set():
                start = time.monotonic()
                try:
                    await self._run_once()
                except asyncio.CancelledError:
                    logutil.log(
                        self.service_name,
                        "INFO",
                        "🛑",
                        "ChainWorker cancelled (shutdown)",
                    )
                    raise
                except Exception as e:
                    logutil.log(
                        self.service_name,
                        "ERROR",
                        "💥",
                        f"ChainWorker cycle error: {e}",
                    )

                elapsed = time.monotonic() - start
                sleep_for = max(0.0, self.interval_sec - elapsed)

                try:
                    # Sleep, but wake early if stop_event is set
                    await asyncio.wait_for(stop_event.wait(), timeout=sleep_for)
                except asyncio.TimeoutError:
                    # Normal wake-up for next cycle
                    continue

        finally:
            logutil.log(
                self.service_name,
                "INFO",
                "🛑",
                "ChainWorker stopped",
            )