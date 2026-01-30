"""
ADI Exporters - Export ADI snapshots to various formats.

Formats:
- JSON: Primary for AI parsing (structured, typed)
- CSV: For spreadsheet analysis
- TEXT: For clipboard/Vexy paste (human-readable but factual)
"""

import json
import csv
import io
from typing import Dict, Any, List
from datetime import datetime

from .adi_models import AIStructureSnapshot, SCHEMA_VERSION


class BaseExporter:
    """Base class for ADI exporters."""

    def export(self, snapshot: AIStructureSnapshot) -> str:
        """Export snapshot to string. Override in subclasses."""
        raise NotImplementedError


class JSONExporter(BaseExporter):
    """Export ADI snapshot to JSON format."""

    def __init__(self, pretty: bool = True, include_nulls: bool = False):
        self.pretty = pretty
        self.include_nulls = include_nulls

    def export(self, snapshot: AIStructureSnapshot) -> str:
        """Export to JSON string."""
        data = snapshot.to_dict()

        if not self.include_nulls:
            data = self._remove_nulls(data)

        if self.pretty:
            return json.dumps(data, indent=2, default=str)
        return json.dumps(data, default=str)

    def _remove_nulls(self, obj: Any) -> Any:
        """Recursively remove null values from dict."""
        if isinstance(obj, dict):
            return {k: self._remove_nulls(v) for k, v in obj.items() if v is not None}
        elif isinstance(obj, list):
            return [self._remove_nulls(item) for item in obj]
        return obj


class CSVExporter(BaseExporter):
    """Export ADI snapshot to CSV format."""

    def export(self, snapshot: AIStructureSnapshot) -> str:
        """Export to CSV string (flattened structure)."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Flatten the snapshot
        flat = self._flatten(snapshot)

        # Write header and data
        writer.writerow(flat.keys())
        writer.writerow(flat.values())

        return output.getvalue()

    def export_multiple(self, snapshots: List[AIStructureSnapshot]) -> str:
        """Export multiple snapshots to CSV."""
        if not snapshots:
            return ""

        output = io.StringIO()
        writer = csv.writer(output)

        # Get headers from first snapshot
        first_flat = self._flatten(snapshots[0])
        writer.writerow(first_flat.keys())

        # Write all rows
        for snapshot in snapshots:
            flat = self._flatten(snapshot)
            writer.writerow(flat.values())

        return output.getvalue()

    def _flatten(self, snapshot: AIStructureSnapshot) -> Dict[str, Any]:
        """Flatten snapshot to single-level dict for CSV."""
        flat = {
            "timestamp_utc": snapshot.timestamp_utc.isoformat(),
            "symbol": snapshot.symbol,
            "session": snapshot.session,
            "schema_version": snapshot.schema_version,
            "snapshot_id": snapshot.snapshot_id,
            "dte": snapshot.dte,
        }

        # Price state
        flat.update({
            "spot_price": snapshot.price_state.spot_price,
            "session_high": snapshot.price_state.session_high,
            "session_low": snapshot.price_state.session_low,
            "vwap": snapshot.price_state.vwap,
            "distance_from_vwap": snapshot.price_state.distance_from_vwap,
            "intraday_range": snapshot.price_state.intraday_range,
        })

        # Volatility
        flat.update({
            "call_iv_atm": snapshot.volatility_state.call_iv_atm,
            "put_iv_atm": snapshot.volatility_state.put_iv_atm,
            "iv_skew": snapshot.volatility_state.iv_skew,
            "iv_rv_ratio": snapshot.volatility_state.iv_rv_ratio,
            "vol_regime": snapshot.volatility_state.vol_regime,
        })

        # Gamma
        flat.update({
            "net_gex": snapshot.gamma_structure.net_gex,
            "zero_gamma_level": snapshot.gamma_structure.zero_gamma_level,
            "gamma_magnet": snapshot.gamma_structure.active_gamma_magnet,
            "gex_ratio": snapshot.gamma_structure.gex_ratio,
        })

        # Auction
        flat.update({
            "poc": snapshot.auction_structure.poc,
            "vah": snapshot.auction_structure.value_area_high,
            "val": snapshot.auction_structure.value_area_low,
            "rotation_state": snapshot.auction_structure.rotation_state,
            "auction_state": snapshot.auction_structure.auction_state,
        })

        # Session
        flat.update({
            "minutes_since_open": snapshot.session_context.minutes_since_open,
            "minutes_to_close": snapshot.session_context.minutes_to_close,
            "session_phase": snapshot.session_context.session_phase,
            "is_rth": snapshot.session_context.is_rth,
        })

        # MEL
        flat.update({
            "gamma_effectiveness": snapshot.mel_scores.gamma_effectiveness,
            "gamma_state": snapshot.mel_scores.gamma_state,
            "vp_effectiveness": snapshot.mel_scores.volume_profile_effectiveness,
            "vp_state": snapshot.mel_scores.volume_profile_state,
            "liquidity_effectiveness": snapshot.mel_scores.liquidity_effectiveness,
            "liquidity_state": snapshot.mel_scores.liquidity_state,
            "volatility_effectiveness": snapshot.mel_scores.volatility_effectiveness,
            "volatility_state": snapshot.mel_scores.volatility_state,
            "session_effectiveness": snapshot.mel_scores.session_effectiveness,
            "session_state": snapshot.mel_scores.session_state,
            "global_integrity": snapshot.mel_scores.global_structure_integrity,
            "coherence_state": snapshot.mel_scores.coherence_state,
        })

        # Event flags (as comma-separated)
        flat["event_flags"] = ",".join(snapshot.event_flags) if snapshot.event_flags else ""

        return flat


class TextExporter(BaseExporter):
    """
    Export ADI snapshot to plain text format.

    Designed for clipboard copy and paste into Vexy or other AI assistants.
    Human-readable but factual - no interpretation.
    """

    def export(self, snapshot: AIStructureSnapshot) -> str:
        """Export to plain text string."""
        lines = []

        # Header
        lines.append(f"=== FOTW Market Snapshot ===")
        lines.append(f"Symbol: {snapshot.symbol}")
        lines.append(f"Time: {snapshot.timestamp_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        lines.append(f"Session: {snapshot.session}")
        if snapshot.dte is not None:
            lines.append(f"DTE: {snapshot.dte}")
        if snapshot.event_flags:
            lines.append(f"Events: {', '.join(snapshot.event_flags)}")
        lines.append("")

        # Price State
        lines.append("--- PRICE ---")
        ps = snapshot.price_state
        if ps.spot_price:
            lines.append(f"Spot: {ps.spot_price:.2f}")
        if ps.session_high and ps.session_low:
            lines.append(f"Range: {ps.session_low:.2f} - {ps.session_high:.2f}")
        if ps.vwap:
            lines.append(f"VWAP: {ps.vwap:.2f}")
            if ps.distance_from_vwap:
                lines.append(f"Distance from VWAP: {ps.distance_from_vwap:+.2f}")
        lines.append("")

        # Gamma Structure
        lines.append("--- GAMMA ---")
        gs = snapshot.gamma_structure
        if gs.net_gex:
            lines.append(f"Net GEX: {gs.net_gex:,.0f}")
        if gs.zero_gamma_level:
            lines.append(f"Zero Gamma: {gs.zero_gamma_level:.2f}")
        if gs.active_gamma_magnet:
            lines.append(f"Gamma Magnet: {gs.active_gamma_magnet:.2f}")
        if gs.high_gamma_strikes:
            lines.append(f"High Gamma Strikes: {', '.join(f'{s:.0f}' for s in gs.high_gamma_strikes[:3])}")
        lines.append("")

        # Auction Structure
        lines.append("--- VOLUME PROFILE ---")
        auc = snapshot.auction_structure
        if auc.poc:
            lines.append(f"POC: {auc.poc:.2f}")
        if auc.value_area_high and auc.value_area_low:
            lines.append(f"Value Area: {auc.value_area_low:.2f} - {auc.value_area_high:.2f}")
        if auc.auction_state:
            lines.append(f"Auction State: {auc.auction_state}")
        lines.append("")

        # Volatility
        lines.append("--- VOLATILITY ---")
        vs = snapshot.volatility_state
        if vs.call_iv_atm:
            lines.append(f"IV ATM (Call): {vs.call_iv_atm:.1f}%")
        if vs.put_iv_atm:
            lines.append(f"IV ATM (Put): {vs.put_iv_atm:.1f}%")
        if vs.iv_rv_ratio:
            lines.append(f"IV/RV Ratio: {vs.iv_rv_ratio:.2f}")
        if vs.vol_regime:
            lines.append(f"Vol Regime: {vs.vol_regime}")
        lines.append("")

        # MEL Scores
        lines.append("--- MODEL EFFECTIVENESS (MEL) ---")
        mel = snapshot.mel_scores
        if mel.global_structure_integrity is not None:
            lines.append(f"Global Integrity: {mel.global_structure_integrity:.0f}%")
        if mel.gamma_effectiveness is not None:
            lines.append(f"Gamma: {mel.gamma_effectiveness:.0f}% ({mel.gamma_state})")
        if mel.volume_profile_effectiveness is not None:
            lines.append(f"Volume Profile: {mel.volume_profile_effectiveness:.0f}% ({mel.volume_profile_state})")
        if mel.liquidity_effectiveness is not None:
            lines.append(f"Liquidity: {mel.liquidity_effectiveness:.0f}% ({mel.liquidity_state})")
        if mel.volatility_effectiveness is not None:
            lines.append(f"Volatility: {mel.volatility_effectiveness:.0f}% ({mel.volatility_state})")
        if mel.coherence_state:
            lines.append(f"Coherence: {mel.coherence_state}")
        lines.append("")

        # Session Context
        lines.append("--- SESSION ---")
        sc = snapshot.session_context
        if sc.session_phase:
            lines.append(f"Phase: {sc.session_phase}")
        if sc.minutes_since_open is not None:
            lines.append(f"Minutes Since Open: {sc.minutes_since_open}")
        if sc.minutes_to_close is not None:
            lines.append(f"Minutes to Close: {sc.minutes_to_close}")
        lines.append("")

        # User Context (if present)
        if snapshot.user_context:
            lines.append("--- USER CONTEXT ---")
            uc = snapshot.user_context
            if uc.selected_tile:
                tile = uc.selected_tile
                lines.append(f"Selected Tile: {tile.get('strike', 'N/A')} {tile.get('side', 'N/A')}")
            if uc.open_trades:
                lines.append(f"Open Trades: {len(uc.open_trades)}")
            if uc.active_alerts:
                lines.append(f"Active Alerts: {len(uc.active_alerts)}")
            lines.append("")

        # Footer
        lines.append(f"Schema: {snapshot.schema_version}")
        lines.append(f"ID: {snapshot.snapshot_id}")

        return "\n".join(lines)


def get_exporter(format: str) -> BaseExporter:
    """Factory function to get exporter by format name."""
    exporters = {
        "json": JSONExporter(),
        "csv": CSVExporter(),
        "text": TextExporter(),
    }
    return exporters.get(format.lower(), JSONExporter())
