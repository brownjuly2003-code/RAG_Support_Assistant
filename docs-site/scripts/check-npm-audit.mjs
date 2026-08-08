/**
 * Plan DEP-01: fail-closed npm audit gate with dated reachability exceptions.
 *
 * - critical: always fail
 * - high: fail unless a non-expired exception covers the package
 * - moderate: fail unless covered by exception
 * - low: fail unless covered (keeps exceptions honest) OR allow if max_severity on exception is low+
 *
 * Usage: node scripts/check-npm-audit.mjs
 * Expects: package-lock present; runs `npm audit --json`.
 */
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const EXCEPTIONS_PATH = join(ROOT, "npm-audit-exceptions.json");

const SEVERITY_RANK = { info: 0, low: 1, moderate: 2, high: 3, critical: 4 };

function todayUtc() {
  return new Date().toISOString().slice(0, 10);
}

function loadExceptions() {
  const raw = JSON.parse(readFileSync(EXCEPTIONS_PATH, "utf8"));
  if (raw.schema_version !== 1) {
    throw new Error(`unsupported exceptions schema_version=${raw.schema_version}`);
  }
  if (!Array.isArray(raw.exceptions)) {
    throw new Error("exceptions must be an array");
  }
  return raw;
}

function isExpired(expires, today) {
  if (!expires || typeof expires !== "string") {
    return true;
  }
  return expires < today;
}

function runAuditJson() {
  const result = spawnSync("npm", ["audit", "--json"], {
    cwd: ROOT,
    encoding: "utf8",
    shell: true,
    maxBuffer: 20 * 1024 * 1024,
  });
  // npm audit exits non-zero when vulns exist; still parse stdout.
  const stdout = result.stdout || "";
  if (!stdout.trim()) {
    throw new Error(
      `npm audit produced no JSON (status=${result.status}): ${result.stderr || ""}`,
    );
  }
  return JSON.parse(stdout);
}

function exceptionCovers(exc, pkgName, severity, today) {
  if (exc.package !== pkgName) {
    return false;
  }
  if (isExpired(exc.expires, today)) {
    return false;
  }
  const maxSev = String(exc.max_severity || "moderate").toLowerCase();
  const maxRank = SEVERITY_RANK[maxSev];
  const sevRank = SEVERITY_RANK[severity] ?? 99;
  if (maxRank === undefined) {
    return false;
  }
  // Exception may cover severities up to and including max_severity.
  return sevRank <= maxRank;
}

function main() {
  const today = todayUtc();
  const registry = loadExceptions();
  const audit = runAuditJson();
  const vulns = audit.vulnerabilities || {};
  const meta = audit.metadata?.vulnerabilities || {};

  const uncovered = [];
  const covered = [];
  const expiredHits = [];

  for (const [pkgName, info] of Object.entries(vulns)) {
    const severity = String(info.severity || "info").toLowerCase();
    if (severity === "info") {
      continue;
    }
    if (severity === "critical") {
      uncovered.push({ package: pkgName, severity, reason: "critical never allowed" });
      continue;
    }
    const match = (registry.exceptions || []).find((exc) =>
      exceptionCovers(exc, pkgName, severity, today),
    );
    if (match) {
      covered.push({
        package: pkgName,
        severity,
        expires: match.expires,
        reason: match.reason,
      });
      continue;
    }
    // Check if an exception exists but expired (better error message).
    const expired = (registry.exceptions || []).find(
      (exc) => exc.package === pkgName && isExpired(exc.expires, today),
    );
    if (expired) {
      expiredHits.push({
        package: pkgName,
        severity,
        expires: expired.expires,
      });
    }
    uncovered.push({
      package: pkgName,
      severity,
      reason: expired
        ? `exception expired on ${expired.expires}`
        : "no dated reachability exception",
    });
  }

  const summary = {
    date: today,
    metadata: meta,
    covered_count: covered.length,
    uncovered_count: uncovered.length,
    exceptions_file: "npm-audit-exceptions.json",
  };

  console.log(JSON.stringify({ summary, covered, uncovered, expiredHits }, null, 2));

  if (uncovered.length > 0) {
    console.error(
      `\nDEP-01 FAIL: ${uncovered.length} advisory package(s) lack a valid dated exception ` +
        `(or are critical). High/critical must be fixed or explicitly excepted with expiry.`,
    );
    process.exit(1);
  }

  // Hard posture: zero high/critical in metadata after exceptions applied to packages.
  const highOrCrit = Number(meta.high || 0) + Number(meta.critical || 0);
  if (highOrCrit > 0) {
    // Package-level exceptions may cover them; if any high remains uncovered we already failed.
    // If high exists but all packages covered, still warn loudly — DEP-01 prefers zero high.
    console.error(
      `\nDEP-01 FAIL: npm audit still reports high=${meta.high} critical=${meta.critical}. ` +
        `Refresh lock or add temporary high exceptions with expiry (prefer fix).`,
    );
    process.exit(1);
  }

  console.error(
    `DEP-01 PASS: high=0 critical=0; ${covered.length} residual low/moderate covered by dated exceptions.`,
  );
  process.exit(0);
}

try {
  main();
} catch (err) {
  console.error(`DEP-01 FAIL: ${err && err.message ? err.message : err}`);
  process.exit(1);
}
