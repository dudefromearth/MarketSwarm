// services/sse/src/econ/scheduleBuilder.js
// UERS v1.1 — EconRollingScheduleBuilder
//
// Generates a rolling economic event schedule from DB-stored cadence rules,
// writes it atomically to Redis for consumption by MarketStateEngine.

import { getPool, isDbAvailable } from "../db/index.js";
import { getMarketRedis } from "../redis.js";

const REDIS_KEY = "massive:econ:schedule:rolling:v1";
const TTL_SECONDS = 10 * 86400; // 10 days

// US market holidays 2025-2026 (mirrors market_state.py)
const US_HOLIDAYS = new Set([
  // 2025
  "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18",
  "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01",
  "2025-11-27", "2025-12-25",
  // 2026
  "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
  "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
  "2026-11-26", "2026-12-25",
]);

/**
 * Format a Date as "YYYY-MM-DD" in ET.
 */
function formatDateET(d) {
  // d is already a Date representing midnight ET via manual construction
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * Get current date in ET as { year, month, day } + a Date object.
 */
function nowET() {
  const str = new Date().toLocaleString("en-US", { timeZone: "America/New_York" });
  const d = new Date(str);
  return {
    year: d.getFullYear(),
    month: d.getMonth(), // 0-indexed
    day: d.getDate(),
    date: d,
  };
}

/**
 * Build a Date from year/month/day (local).
 */
function makeDate(year, month, day) {
  return new Date(year, month, day);
}

/**
 * Generate dates in window [start, start + windowDays).
 */
function dateRange(startDate, windowDays) {
  const dates = [];
  for (let i = 0; i < windowDays; i++) {
    const d = new Date(startDate);
    d.setDate(d.getDate() + i);
    dates.push(d);
  }
  return dates;
}

/**
 * Find the first Friday of a given month/year.
 */
function firstFriday(year, month) {
  const d = new Date(year, month, 1);
  const dayOfWeek = d.getDay(); // 0=Sun
  const offset = (5 - dayOfWeek + 7) % 7; // days until Friday
  d.setDate(1 + offset);
  return d;
}

/**
 * Find the nth occurrence of a weekday in a given month.
 * weekday: 0=Sun ... 6=Sat, n: 1-based
 */
function nthWeekday(year, month, weekday, n) {
  const d = new Date(year, month, 1);
  const dayOfWeek = d.getDay();
  const offset = (weekday - dayOfWeek + 7) % 7;
  d.setDate(1 + offset + (n - 1) * 7);
  // Verify still in same month
  if (d.getMonth() !== month) return null;
  return d;
}

/**
 * Resolve dates for an indicator within the window.
 *
 * @param {Object} indicator - DB row with cadence, rule_json, release_time_et
 * @param {Date} windowStart
 * @param {number} windowDays
 * @returns {Array<{ date: string, time_et: string }>}
 */
function resolveDates(indicator, windowStart, windowDays) {
  const { cadence, rule_json } = indicator;
  if (!cadence || cadence === "manual") return [];

  let rule;
  try {
    rule = typeof rule_json === "string" ? JSON.parse(rule_json) : rule_json;
  } catch {
    return [];
  }
  if (!rule) return [];

  const windowEnd = new Date(windowStart);
  windowEnd.setDate(windowEnd.getDate() + windowDays);

  const startStr = formatDateET(windowStart);
  const endStr = formatDateET(windowEnd);
  const timeEt = rule.time_et || indicator.release_time_et || "08:30";
  const results = [];

  switch (rule.type || cadence) {
    case "fixed_dates": {
      const dates = rule.dates || [];
      for (const ds of dates) {
        if (ds >= startStr && ds < endStr) {
          results.push({ date: ds, time_et: timeEt });
        }
      }
      break;
    }

    case "first_friday": {
      // Check each month that overlaps the window
      const months = getMonthsInWindow(windowStart, windowDays);
      for (const { year, month } of months) {
        const ff = firstFriday(year, month);
        const ffStr = formatDateET(ff);
        if (ffStr >= startStr && ffStr < endStr) {
          // Skip if holiday — shift to preceding Thursday
          if (US_HOLIDAYS.has(ffStr)) {
            const thu = new Date(ff);
            thu.setDate(thu.getDate() - 1);
            const thuStr = formatDateET(thu);
            if (thuStr >= startStr && thuStr < endStr) {
              results.push({ date: thuStr, time_et: timeEt });
            }
          } else {
            results.push({ date: ffStr, time_et: timeEt });
          }
        }
      }
      break;
    }

    case "nth_weekday": {
      const { weekday, n } = rule;
      if (weekday === undefined || n === undefined) break;
      const months = getMonthsInWindow(windowStart, windowDays);
      for (const { year, month } of months) {
        const d = nthWeekday(year, month, weekday, n);
        if (!d) continue;
        const ds = formatDateET(d);
        if (ds >= startStr && ds < endStr) {
          results.push({ date: ds, time_et: timeEt });
        }
      }
      break;
    }

    case "weekly": {
      const { weekday } = rule;
      if (weekday === undefined) break;
      const range = dateRange(windowStart, windowDays);
      for (const d of range) {
        if (d.getDay() === weekday) {
          const ds = formatDateET(d);
          if (!US_HOLIDAYS.has(ds)) {
            results.push({ date: ds, time_et: timeEt });
          }
        }
      }
      break;
    }
  }

  return results;
}

/**
 * Get distinct year/month pairs that overlap [start, start + days).
 */
function getMonthsInWindow(start, days) {
  const seen = new Set();
  const months = [];
  for (let i = 0; i < days; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    const key = `${d.getFullYear()}-${d.getMonth()}`;
    if (!seen.has(key)) {
      seen.add(key);
      months.push({ year: d.getFullYear(), month: d.getMonth() });
    }
  }
  return months;
}

/**
 * Build the rolling schedule artifact and write to Redis.
 *
 * @param {Object} opts
 * @param {number} opts.windowDays - Number of days in the rolling window (default 7)
 * @returns {Object} Summary of the build
 */
export async function buildRollingSchedule({ windowDays = 7 } = {}) {
  if (!isDbAvailable()) {
    throw new Error("Database unavailable");
  }

  const pool = getPool();
  const redis = getMarketRedis();
  if (!redis) {
    throw new Error("Redis unavailable");
  }

  // Fetch all active indicators with cadence rules
  const [indicators] = await pool.execute(`
    SELECT \`key\`, name, rating, tier, release_time_et, cadence, rule_json
    FROM economic_indicators
    WHERE is_active = 1
  `);

  const et = nowET();
  const windowStart = makeDate(et.year, et.month, et.day);
  const windowStartStr = formatDateET(windowStart);
  const windowEndDate = new Date(windowStart);
  windowEndDate.setDate(windowEndDate.getDate() + windowDays);
  const windowEndStr = formatDateET(windowEndDate);

  // Build days map
  const days = {};
  let eventCount = 0;

  for (const ind of indicators) {
    const dates = resolveDates(ind, windowStart, windowDays);
    for (const { date, time_et } of dates) {
      if (!days[date]) days[date] = { events: [] };
      days[date].events.push({
        indicator_key: ind.key,
        name: ind.name,
        time_et,
        rating: ind.rating,
        tier: ind.tier,
      });
      eventCount++;
    }
  }

  // Sort events within each day by time
  for (const day of Object.values(days)) {
    day.events.sort((a, b) => a.time_et.localeCompare(b.time_et));
  }

  // Generate ISO timestamp in ET
  const generatedAt = new Date().toLocaleString("en-US", { timeZone: "America/New_York" });
  const genDate = new Date(generatedAt);
  const isoGenerated = genDate.toISOString().replace("Z", "-05:00");

  const artifact = {
    schema_version: 1,
    window_start: windowStartStr,
    window_end: windowEndStr,
    generated_at: isoGenerated,
    indicator_count: indicators.length,
    days,
  };

  // Write atomically to Redis with TTL
  await redis.set(REDIS_KEY, JSON.stringify(artifact), "EX", TTL_SECONDS);

  console.log(
    `[econ-schedule] Built rolling schedule: ${windowStartStr} → ${windowEndStr}, ` +
    `${eventCount} events from ${indicators.length} indicators`
  );

  return {
    generated_at: isoGenerated,
    window_start: windowStartStr,
    window_end: windowEndStr,
    event_count: eventCount,
  };
}

/**
 * Start the daily scheduler. Checks every minute if it's 04:00 ET
 * and hasn't built today yet.
 */
export function startScheduleBuilder() {
  let lastBuildDate = null;

  const check = async () => {
    try {
      const et = nowET();
      const hour = et.date.getHours();
      const todayStr = formatDateET(makeDate(et.year, et.month, et.day));

      // Build at 04:00 ET if not already built today
      if (hour === 4 && lastBuildDate !== todayStr) {
        console.log("[econ-schedule] Daily build triggered at 04:00 ET");
        await buildRollingSchedule({ windowDays: 7 });
        lastBuildDate = todayStr;
      }
    } catch (err) {
      console.error("[econ-schedule] Daily build failed:", err.message);
    }
  };

  // Check every 60 seconds
  const intervalId = setInterval(check, 60_000);

  // Also do an initial build on startup
  buildRollingSchedule({ windowDays: 7 }).catch((err) => {
    console.warn("[econ-schedule] Initial build failed (will retry at 04:00 ET):", err.message);
  });

  console.log("[econ-schedule] Daily scheduler started (builds at 04:00 ET)");
  return intervalId;
}
