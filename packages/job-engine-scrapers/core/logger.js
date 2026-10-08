/**
 * Structured logger for scrapers.
 *
 * Provides consistent log output with timestamps, scraper name, and levels.
 *
 * Usage:
 *   const log = require("./logger")("justjoin_it");
 *   log.info("Starting…");
 *   log.warn("Rate limited");
 *   log.error("Failed", err);
 */

const LEVELS = { debug: 0, info: 1, warn: 2, error: 3 };
const COLORS = { debug: "\x1b[90m", info: "\x1b[36m", warn: "\x1b[33m", error: "\x1b[31m" };
const RESET = "\x1b[0m";

// Structured event marker consumed by the Python dashboard (scraper_runner.py).
// Must match EVENT_MARKER in run.js. Every warn/error also emits a
// machine-readable "issue" event so the dashboard can collect issues without
// parsing human log text.
const EVENT_MARKER = "##SCRAPER_EVENT##";

function timestamp() {
  return new Date().toISOString().replace("T", " ").slice(0, 19);
}

function createLogger(name) {
  const logLevel = (process.env.LOG_LEVEL || "info").toLowerCase();
  const minLevel = LEVELS[logLevel] ?? LEVELS.info;

  function log(level, msg, extra) {
    if (LEVELS[level] < minLevel) return;
    const prefix = `${COLORS[level]}[${timestamp()}] [${level.toUpperCase()}] [${name}]${RESET}`;
    let extraStr = "";
    if (extra !== undefined && extra !== null) {
      try {
        extraStr = ` ${typeof extra === "object" ? JSON.stringify(extra) : extra}`;
      } catch { /* JSON.stringify failed — use fallback */
        extraStr = ` ${String(extra)}`;
      }
    }
    const line = `${prefix} ${msg}${extraStr}`;
    if (level === "error") {
      console.error(line);
    } else if (level === "warn") {
      console.warn(line);
    } else {
      console.log(line);
    }
    if (level === "warn" || level === "error") {
      const event = {
        type: "issue",
        severity: level === "warn" ? "warning" : "error",
        source: name,
        message: `${msg}${extraStr}`,
      };
      try {
        console.log(`${EVENT_MARKER} ${JSON.stringify(event)}`);
      } catch { /* JSON.stringify failed — use fallback */
        console.error(`${EVENT_MARKER} ${JSON.stringify({ type: "issue", severity: level === "warn" ? "warning" : "error", source: name, message: msg })}`);
      }
    }
  }

  return {
    debug: (msg, extra) => log("debug", msg, extra),
    info: (msg, extra) => log("info", msg, extra),
    warn: (msg, extra) => log("warn", msg, extra),
    error: (msg, extra) => log("error", msg, extra),
    child: (subname) => createLogger(`${name}:${subname}`),
  };
}

module.exports = createLogger;