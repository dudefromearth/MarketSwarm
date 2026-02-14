import { useEffect, useState, useCallback } from "react";

const BASE = "/api/vexy/admin/doctrine";

function useFetch<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(url, { credentials: "include" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      if (!json.success) throw new Error(json.error || "Request failed");
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, loading, error, refetch };
}

export interface DoctrinePlaybookSummary {
  domain: string;
  version: string;
  doctrine_source: string;
  path_runtime_version: string;
  path_runtime_hash: string;
  generated_at: string;
  term_count: number;
  constraint_count: number;
}

export interface PlaybooksResponse {
  success: boolean;
  count: number;
  synchronized: boolean;
  safe_mode: boolean;
  playbooks: DoctrinePlaybookSummary[];
}

export interface TermsResponse {
  success: boolean;
  terms: Record<string, string>;
  count: number;
}

export interface KillSwitchState {
  pde_enabled: boolean;
  overlay_enabled: boolean;
  rv_enabled: boolean;
  lpd_enabled: boolean;
  last_toggled_by: string | null;
  last_toggled_at: number | null;
}

export interface HealthResponse {
  success: boolean;
  health: {
    registry: Record<string, unknown>;
    kill_switch: KillSwitchState;
    governance: {
      lpd_config: Record<string, number>;
      validator_config: Record<string, unknown>;
      thresholds: Record<string, number>;
    };
    pde: { status: string; auto_disabled: boolean };
    aos: { status: string; active_overlays: number };
  };
}

export interface ValidationLogEntry {
  ts: number;
  user_id: number;
  doctrine_mode: string;
  hard_violations: string[];
  soft_warnings: string[];
  regenerated: boolean;
  domain: string;
}

export function useDoctrinePlaybooks() {
  return useFetch<PlaybooksResponse>(`${BASE}/playbooks`);
}

export function useDoctrineTerms() {
  return useFetch<TermsResponse>(`${BASE}/terms`);
}

export function useDoctrineHealth() {
  return useFetch<HealthResponse>(`${BASE}/health`);
}

export function useValidationLog() {
  return useFetch<{ success: boolean; entries: ValidationLogEntry[] }>(
    `${BASE}/validation-log`
  );
}

export function useKillSwitch() {
  return useFetch<{ success: boolean; kill_switch: KillSwitchState }>(
    `${BASE}/kill-switch`
  );
}

export async function toggleKillSwitch(
  subsystem: string,
  enabled: boolean
): Promise<{ success: boolean; changed: boolean }> {
  const res = await fetch(`${BASE}/kill-switch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ subsystem, enabled, admin_user: "admin" }),
  });
  return res.json();
}

export async function updateLPDConfig(
  updates: Record<string, number>
): Promise<Record<string, number>> {
  const res = await fetch(`${BASE}/lpd/config`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(updates),
  });
  const json = await res.json();
  return json.config;
}

export async function updateValidatorConfig(
  updates: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/validator/config`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(updates),
  });
  const json = await res.json();
  return json.config;
}

export async function updateThresholds(
  updates: Record<string, number>
): Promise<Record<string, number>> {
  const res = await fetch(`${BASE}/thresholds`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(updates),
  });
  const json = await res.json();
  return json.thresholds;
}

// =================================================================
// PDE Pattern Detection Hooks
// =================================================================

export interface PatternAlert {
  category: string;
  confidence: number;
  sample_size: number;
  summary: string;
  ts: number;
  user_id: number;
}

export interface ScanMetrics {
  last_scan_ts: number | null;
  last_scan_users: number;
  last_scan_alerts: number;
  last_scan_latency_ms: number;
  last_scan_users_total: number;
  last_scan_batch_size: number;
  scan_running: boolean;
  scan_cursor: number;
}

export interface PatternsResponse {
  success: boolean;
  patterns: PatternAlert[];
  health: Record<string, unknown>;
}

export interface PatternMetricsResponse {
  success: boolean;
  metrics: Record<string, unknown>;
  scan: ScanMetrics;
}

export function useDoctrinePatterns() {
  return useFetch<PatternsResponse>(`${BASE}/patterns/active`);
}

export function useDoctrinePatternMetrics() {
  return useFetch<PatternMetricsResponse>(`${BASE}/patterns/metrics`);
}

// =================================================================
// AOS Overlay Hooks
// =================================================================

export interface OverlayRecord {
  user_id: number;
  category: string;
  label: string;
  summary: string;
  confidence: number;
  created_at: number;
  expires_at: number;
}

export interface OverlaysResponse {
  success: boolean;
  overlays: OverlayRecord[];
  stats: {
    active_overlays: number;
    suppressed_users: number;
    active_cooldowns: number;
  };
}

export function useDoctrineOverlays() {
  return useFetch<OverlaysResponse>(`${BASE}/overlays/active`);
}

export async function suppressUserOverlay(
  userId: number
): Promise<{ success: boolean }> {
  const res = await fetch(`${BASE}/overlays/${userId}`, {
    method: "DELETE",
    credentials: "include",
  });
  return res.json();
}
