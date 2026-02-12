#!/usr/bin/env node
/**
 * UERS v1.1 — One-time backfill script for economic indicator cadence rules.
 *
 * Reads pre-computed rules from econBackfillData.json and updates
 * the economic_indicators table with release_time_et, cadence, rule_json.
 *
 * Usage: node services/sse/src/db/econBackfill.js
 */

import { readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import mysql from "mysql2/promise";

const __dirname = dirname(fileURLToPath(import.meta.url));

async function main() {
  // Read backfill data
  const dataPath = join(__dirname, "econBackfillData.json");
  const data = JSON.parse(readFileSync(dataPath, "utf-8"));
  const rules = data.rules;

  console.log(`[backfill] Loaded ${rules.length} indicator rules`);

  // Connect to DB (use DATABASE_URL from env or default)
  const dbUrl =
    process.env.DATABASE_URL ||
    "mysql+pymysql://fotw_app:PfedKtaTaAa2iV21QTZp@127.0.0.1:3306/fotw_app";
  const url = new URL(dbUrl.replace("mysql+pymysql://", "mysql://"));

  const pool = mysql.createPool({
    host: url.hostname,
    port: parseInt(url.port, 10) || 3306,
    user: url.username,
    password: decodeURIComponent(url.password),
    database: url.pathname.slice(1),
    waitForConnections: true,
    connectionLimit: 5,
  });

  let updated = 0;
  let skipped = 0;

  for (const rule of rules) {
    const ruleJsonStr = JSON.stringify(rule.rule_json);

    try {
      const [result] = await pool.execute(
        "UPDATE economic_indicators SET release_time_et = ?, cadence = ?, rule_json = ? WHERE `key` = ?",
        [rule.release_time_et, rule.cadence, ruleJsonStr, rule.key]
      );

      if (result.affectedRows > 0) {
        console.log(`  [ok] ${rule.key}: cadence=${rule.cadence}, time=${rule.release_time_et}`);
        updated++;
      } else {
        console.log(`  [skip] ${rule.key}: not found in DB`);
        skipped++;
      }
    } catch (err) {
      console.error(`  [err] ${rule.key}: ${err.message}`);
    }
  }

  console.log(`\n[backfill] Done: ${updated} updated, ${skipped} skipped`);

  // Verify
  const [rows] = await pool.execute(
    "SELECT `key`, cadence, release_time_et FROM economic_indicators WHERE cadence IS NOT NULL ORDER BY `key`"
  );
  console.log(`[backfill] Verification: ${rows.length} indicators now have cadence rules`);

  await pool.end();
}

main().catch((err) => {
  console.error("[backfill] Fatal error:", err);
  process.exit(1);
});
