export type LogLevel = "debug" | "info" | "warn" | "error";

const SENSITIVE_KEY = /token|secret|api[_-]?key|authorization|password/i;

/** Replace values of keys that look like secrets before logs are emitted. */
export function redactSensitive(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(redactSensitive);
  }
  if (value !== null && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      out[key] = SENSITIVE_KEY.test(key) ? "[REDACTED]" : redactSensitive(nested);
    }
    return out;
  }
  return value;
}

function emit(level: LogLevel, message: string, extra?: Record<string, unknown>) {
  const safeExtra =
    extra === undefined ? undefined : (redactSensitive(extra) as Record<string, unknown>);
  const payload = JSON.stringify({ level, message, ...safeExtra });
  if (level === "error") {
    console.error(payload);
    return;
  }
  if (level === "warn") {
    console.warn(payload);
    return;
  }
  console.info(payload);
}

/** Structured logger. Extra fields matching secret-like keys are redacted. */
export const logger = {
  debug: (message: string, extra?: Record<string, unknown>) => {
    if ((process.env.LOG_LEVEL ?? "info") === "debug") {
      emit("debug", message, extra);
    }
  },
  info: (message: string, extra?: Record<string, unknown>) => {
    emit("info", message, extra);
  },
  warn: (message: string, extra?: Record<string, unknown>) => {
    emit("warn", message, extra);
  },
  error: (message: string, extra?: Record<string, unknown>) => {
    emit("error", message, extra);
  },
};
