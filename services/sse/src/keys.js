// services/sse/src/keys.js
// Key resolver - derives Redis keys from config.models.consumes

/**
 * Builds a key map from config.models.consumes
 * Maps model names to their base key patterns
 */
export function buildKeyMap(config) {
  const keyMap = {};

  for (const entry of config.models?.consumes || []) {
    const key = entry.key;

    // Extract model name from key pattern
    // e.g., "massive:model:spot" -> "spot"
    // e.g., "massive:gex:model" -> "gex"
    // e.g., "massive:heatmap:model:{symbol}:latest" -> "heatmap"
    // e.g., "vexy:model:playbyplay" -> "vexy"

    if (key.startsWith("massive:model:spot")) {
      keyMap.spot = key;
    } else if (key.startsWith("massive:gex:model")) {
      keyMap.gex = key;
    } else if (key.startsWith("massive:heatmap:model")) {
      keyMap.heatmap = key;
    } else if (key.startsWith("massive:heatmap:replay")) {
      keyMap.heatmap_replay = key;
    } else if (key.startsWith("massive:market_mode:model")) {
      keyMap.market_mode = key;
    } else if (key.startsWith("massive:vix_regime:model")) {
      keyMap.vix_regime = key;
    } else if (key.startsWith("massive:volume_profile:model")) {
      keyMap.volume_profile = key;
    } else if (key.startsWith("massive:bias_lfi:model")) {
      keyMap.bias_lfi = key;
    } else if (key.startsWith("vexy:model:playbyplay")) {
      keyMap.vexy = key;
    } else if (key.startsWith("copilot:alerts:events")) {
      keyMap.alerts_events = key;
    } else if (key.startsWith("copilot:alerts:latest")) {
      keyMap.alerts_latest = key;
    }
  }

  return keyMap;
}

/**
 * Key resolver class - provides methods to derive actual Redis keys from config patterns
 */
export class KeyResolver {
  constructor(config) {
    this.keyMap = buildKeyMap(config);
  }

  // Spot keys
  spotPattern() {
    return this.keyMap.spot ? `${this.keyMap.spot}:*` : "massive:model:spot:*";
  }

  spotKey(symbol) {
    return this.keyMap.spot ? `${this.keyMap.spot}:${symbol}` : `massive:model:spot:${symbol}`;
  }

  spotTrailKey(symbol) {
    return `${this.spotKey(symbol)}:trail`;
  }

  // GEX keys
  gexPattern() {
    return this.keyMap.gex ? `${this.keyMap.gex}:*` : "massive:gex:model:*";
  }

  gexCallsKey(symbol) {
    return this.keyMap.gex ? `${this.keyMap.gex}:${symbol}:calls` : `massive:gex:model:${symbol}:calls`;
  }

  gexPutsKey(symbol) {
    return this.keyMap.gex ? `${this.keyMap.gex}:${symbol}:puts` : `massive:gex:model:${symbol}:puts`;
  }

  // Heatmap keys
  heatmapPattern() {
    // Pattern for scanning all heatmaps
    return "massive:heatmap:model:*:latest";
  }

  heatmapKey(symbol, strategy = "latest") {
    const base = this.keyMap.heatmap || "massive:heatmap:model:{symbol}:latest";
    return base.replace("{symbol}", symbol).replace(":latest", `:${strategy}`);
  }

  heatmapLatestKey(symbol) {
    return this.heatmapKey(symbol, "latest");
  }

  heatmapDiffChannel(symbol) {
    return `massive:heatmap:diff:${symbol}`;
  }

  // Vexy keys
  vexyEpochKey() {
    return this.keyMap.vexy ? `${this.keyMap.vexy}:epoch:latest` : "vexy:model:playbyplay:epoch:latest";
  }

  vexyEventKey() {
    return this.keyMap.vexy ? `${this.keyMap.vexy}:event:latest` : "vexy:model:playbyplay:event:latest";
  }

  vexyChannel() {
    return "vexy:playbyplay";
  }

  vexyTodayKey() {
    // Today's message list - uses UTC date
    const today = new Date().toISOString().split('T')[0];
    return `vexy:messages:${today}`;
  }

  // Market mode
  marketModeKey() {
    return this.keyMap.market_mode ? `${this.keyMap.market_mode}:latest` : "massive:market_mode:model:latest";
  }

  // VIX regime
  vixRegimeKey() {
    return this.keyMap.vix_regime ? `${this.keyMap.vix_regime}:latest` : "massive:vix_regime:model:latest";
  }

  // Volume profile
  volumeProfileKey(symbol = "spx") {
    // Volume profile uses hash keys
    return `massive:volume_profile:${symbol}`;
  }

  volumeProfileMetaKey(symbol = "spx") {
    return `${this.volumeProfileKey(symbol)}:meta`;
  }

  // Bias/LFI
  biasLfiKey() {
    return this.keyMap.bias_lfi ? `${this.keyMap.bias_lfi}:latest` : "massive:bias_lfi:model:latest";
  }

  // Alerts - keys from copilot service
  alertsChannel() {
    return this.keyMap.alerts_events || "copilot:alerts:events";
  }

  alertsLatestKey() {
    return this.keyMap.alerts_latest || "copilot:alerts:latest";
  }

  alertKey(alertId) {
    const prefix = this.keyMap.alerts_latest
      ? this.keyMap.alerts_latest.replace(":latest", "")
      : "copilot:alerts";
    return `${prefix}:${alertId}`;
  }

  alertsPattern() {
    const prefix = this.keyMap.alerts_latest
      ? this.keyMap.alerts_latest.replace(":latest", "")
      : "copilot:alerts";
    return `${prefix}:*`;
  }

  // Debug: log all resolved keys
  logKeys() {
    console.log("[keys] Resolved key patterns from config:");
    console.log(`  spot pattern: ${this.spotPattern()}`);
    console.log(`  gex pattern: ${this.gexPattern()}`);
    console.log(`  heatmap pattern: ${this.heatmapPattern()}`);
    console.log(`  vexy epoch: ${this.vexyEpochKey()}`);
    console.log(`  vexy event: ${this.vexyEventKey()}`);
    console.log(`  market_mode: ${this.marketModeKey()}`);
    console.log(`  vix_regime: ${this.vixRegimeKey()}`);
    console.log(`  bias_lfi: ${this.biasLfiKey()}`);
    console.log(`  volume_profile: ${this.volumeProfileKey()}`);
    console.log(`  alerts channel: ${this.alertsChannel()}`);
    console.log(`  alerts latest: ${this.alertsLatestKey()}`);
  }
}

// Singleton instance - set by setConfig()
let resolver = null;

export function setConfig(config) {
  resolver = new KeyResolver(config);
  resolver.logKeys();
}

export function getKeys() {
  if (!resolver) {
    throw new Error("KeyResolver not initialized - call setConfig first");
  }
  return resolver;
}
