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
// Playbook Full Content + CRUD Hooks (Phase 1)
// =================================================================

export interface AnnotatedTerm {
  term: string;
  definition: string;
  source: "base" | "admin";
  hidden?: boolean;
}

export interface AnnotatedListItem {
  text: string;
  source: "base" | "admin";
  hidden?: boolean;
}

export interface AnnotatedDefinition {
  value: string;
  source: "base" | "admin";
}

export interface PlaybookFullContent {
  domain: string;
  version: string;
  doctrine_source: string;
  path_runtime_version: string;
  path_runtime_hash: string;
  generated_at: string;
  has_overrides: boolean;
  canonical_terminology: AnnotatedTerm[];
  definitions: Record<string, AnnotatedDefinition>;
  structural_logic: AnnotatedListItem[];
  mechanisms: AnnotatedListItem[];
  constraints: AnnotatedListItem[];
  failure_modes: AnnotatedListItem[];
  non_capabilities: AnnotatedListItem[];
}

export interface PlaybookFullResponse {
  success: boolean;
  playbook: PlaybookFullContent;
}

export function usePlaybookFull(domain: string | null) {
  const url = domain ? `${BASE}/playbooks/${domain}/full` : null;
  const [data, setData] = useState<PlaybookFullResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!url) return;
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
    if (domain) refetch();
  }, [domain, refetch]);

  return { data, loading, error, refetch };
}

export async function updatePlaybookField(
  domain: string,
  field: string,
  data: Record<string, unknown>
): Promise<{ success: boolean; error?: string }> {
  const res = await fetch(`${BASE}/playbooks/${domain}/${field}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function clearPlaybookOverrides(
  domain: string
): Promise<{ success: boolean }> {
  const res = await fetch(`${BASE}/playbooks/${domain}/overrides`, {
    method: "DELETE",
    credentials: "include",
  });
  return res.json();
}

export async function regeneratePlaybooks(): Promise<{
  success: boolean;
  regenerated_count?: number;
  new_hash?: string;
  error?: string;
}> {
  const res = await fetch(`${BASE}/playbooks/regenerate`, {
    method: "POST",
    credentials: "include",
  });
  return res.json();
}

export interface PlaybookDiff {
  domain: string;
  has_overrides: boolean;
  overrides: Record<string, unknown>;
  base: Record<string, unknown>;
  merged: Record<string, unknown>;
}

export function usePlaybookDiff(domain: string | null) {
  const url = domain ? `${BASE}/playbooks/diff/${domain}` : null;
  const [data, setData] = useState<{ success: boolean; diff: PlaybookDiff } | null>(null);
  const [loading, setLoading] = useState(false);

  const refetch = useCallback(async () => {
    if (!url) return;
    setLoading(true);
    try {
      const res = await fetch(url, { credentials: "include" });
      const json = await res.json();
      setData(json);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => {
    if (domain) refetch();
  }, [domain, refetch]);

  return { data, loading, refetch };
}

// =================================================================
// Routing + Test Console Hooks (Phase 2)
// =================================================================

export interface RoutingPattern {
  pattern: string;
  weight: number;
  source: "base" | "admin";
}

export interface RoutingDomainInfo {
  patterns: RoutingPattern[];
  playbook: string;
  admin_patterns: { pattern: string; weight: number }[];
}

export interface RoutingMapResponse {
  success: boolean;
  routing: Record<string, RoutingDomainInfo>;
}

export function useRoutingMap() {
  return useFetch<RoutingMapResponse>(`${BASE}/routing/map`);
}

export async function updateRoutingPatterns(
  domain: string,
  data: { add?: { pattern: string; weight: number }[]; remove?: number[] }
): Promise<{ success: boolean }> {
  const res = await fetch(`${BASE}/routing/${domain}/patterns`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function updatePlaybookMap(
  domain: string,
  playbook: string
): Promise<{ success: boolean }> {
  const res = await fetch(`${BASE}/routing/playbook-map`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ domain, playbook }),
  });
  return res.json();
}

export interface ClassificationTestResult {
  domain: string;
  confidence: number;
  secondary_domain: string | null;
  doctrine_mode: string;
  playbook_domain: string;
  matched_patterns: string[];
  require_playbook: boolean;
}

export async function testClassification(
  message: string
): Promise<{ success: boolean; result: ClassificationTestResult }> {
  const res = await fetch(`${BASE}/routing/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ message }),
  });
  return res.json();
}

// =================================================================
// Term Registry Hooks (Phase 3)
// =================================================================

export interface TermRegistryEntry {
  term: string;
  definition: string;
  playbooks: string[];
  source: "base" | "admin";
}

export interface TermRegistryResponse {
  success: boolean;
  terms: TermRegistryEntry[];
  count: number;
}

export function useTermRegistry() {
  return useFetch<TermRegistryResponse>(`${BASE}/terms/registry`);
}

export async function createTerm(
  term: string,
  definition: string,
  playbooks: string[]
): Promise<{ success: boolean }> {
  const res = await fetch(`${BASE}/terms`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ term, definition, playbooks }),
  });
  return res.json();
}

export async function updateTermRegistry(
  term: string,
  definition: string,
  playbooks: string[]
): Promise<{ success: boolean }> {
  const res = await fetch(`${BASE}/terms/${encodeURIComponent(term)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ definition, playbooks }),
  });
  return res.json();
}

export async function deleteTerm(
  term: string
): Promise<{ success: boolean }> {
  const res = await fetch(`${BASE}/terms/${encodeURIComponent(term)}`, {
    method: "DELETE",
    credentials: "include",
  });
  return res.json();
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
