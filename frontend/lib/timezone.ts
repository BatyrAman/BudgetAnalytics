/**
 * The user's IANA time zone and local-calendar helpers — the single source for
 * every screen. The zone is chosen in Settings and stored only in this browser
 * (S-1); the backend receives it as the `tz` query parameter.
 *
 * The API takes date-time filters as ISO strings; a value without an offset is
 * treated as UTC. To filter by the user's *local* calendar days we always send
 * the zone's explicit offset, e.g. `2026-11-01T00:00:00+05:00` …
 * `2026-11-30T23:59:59.999999+05:00` for Asia/Almaty. Range ends are inclusive
 * (`<=` in the backend) and the backend stores microseconds, so a local day ends
 * at 23:59:59.999999 — otherwise an operation at 23:59:59.5 would be missed.
 */
import { useSyncExternalStore } from "react";

export const DEFAULT_TIMEZONE = "Asia/Almaty";
export const TIMEZONE_STORAGE_KEY = "ba:timezone";
/** Fired in this tab after the zone is saved (the `storage` event covers other tabs). */
export const TIMEZONE_EVENT = "ba:timezone-change";

export function currentTimezone(): string {
  if (typeof window === "undefined") return DEFAULT_TIMEZONE;
  try {
    return window.localStorage.getItem(TIMEZONE_STORAGE_KEY) || DEFAULT_TIMEZONE;
  } catch {
    return DEFAULT_TIMEZONE;
  }
}

/**
 * Saves the zone for this browser and notifies every subscriber in this tab.
 * Throws if the browser refuses storage (private mode); nothing is notified then.
 */
export function setTimezone(timeZone: string): void {
  window.localStorage.setItem(TIMEZONE_STORAGE_KEY, timeZone);
  window.dispatchEvent(new Event(TIMEZONE_EVENT));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(TIMEZONE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(TIMEZONE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/**
 * The user's zone, kept in sync with Settings. `null` during server rendering
 * and hydration, so zone-dependent requests start once, with the real zone.
 */
export function useTimezone(): string | null {
  return useSyncExternalStore(subscribe, currentTimezone, () => null);
}

/** A valid zone: unknown/invalid IANA names fall back to the default. */
export function safeTimezone(timeZone: string): string {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone }).format(0);
    return timeZone;
  } catch {
    return DEFAULT_TIMEZONE;
  }
}

export type LocalDateParts = {
  year: number;
  month: number; // 1–12
  day: number;
  hour?: number;
  minute?: number;
  second?: number;
};

const pad = (value: number, size = 2) => String(value).padStart(size, "0");

/** Wall-clock parts of an instant in a time zone. */
export function zonedParts(instant: Date, timeZone: string): Required<LocalDateParts> {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: safeTimezone(timeZone),
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(instant);
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value ?? 0);
  return {
    year: get("year"),
    month: get("month"),
    day: get("day"),
    hour: get("hour"),
    minute: get("minute"),
    second: get("second"),
  };
}

/** UTC offset of `timeZone` at `instant`, in minutes (east positive; +300 for UTC+05:00). */
export function offsetMinutes(instant: Date, timeZone: string): number {
  const p = zonedParts(instant, timeZone);
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  const wholeSecond = Math.floor(instant.getTime() / 1000) * 1000;
  return Math.round((asUtc - wholeSecond) / 60000);
}

function formatOffset(minutes: number): string {
  const sign = minutes < 0 ? "-" : "+";
  const abs = Math.abs(minutes);
  return `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

/**
 * ISO date-time with the zone's offset for a local wall-clock time. The offset
 * is computed in two passes so that it is correct across DST changes.
 * `fraction` adds sub-second digits (e.g. "999999" for an inclusive day end).
 */
export function zonedIso(local: LocalDateParts, timeZone: string, fraction = ""): string {
  const { year, month, day, hour = 0, minute = 0, second = 0 } = local;
  const guess = Date.UTC(year, month - 1, day, hour, minute, second);
  let offset = offsetMinutes(new Date(guess), timeZone);
  offset = offsetMinutes(new Date(guess - offset * 60000), timeZone);
  return (
    `${pad(year, 4)}-${pad(month)}-${pad(day)}` +
    `T${pad(hour)}:${pad(minute)}:${pad(second)}${fraction ? `.${fraction}` : ""}` +
    formatOffset(offset)
  );
}

const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Parses a real calendar date `YYYY-MM-DD`; null for malformed or impossible dates. */
export function parseLocalDate(value: string): LocalDateParts | null {
  const match = DATE_RE.exec(value);
  if (!match) return null;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const check = new Date(Date.UTC(year, month - 1, day));
  if (check.getUTCMonth() !== month - 1 || check.getUTCDate() !== day) return null;
  return { year, month, day };
}

/** `YYYY-MM-DD` → ISO of local 00:00:00; null for an invalid date. */
export function localDayStart(date: string, timeZone: string): string | null {
  const parts = parseLocalDate(date);
  return parts ? zonedIso({ ...parts, hour: 0, minute: 0, second: 0 }, timeZone) : null;
}

/** `YYYY-MM-DD` → ISO of local 23:59:59.999999 (inclusive end); null for an invalid date. */
export function localDayEnd(date: string, timeZone: string): string | null {
  const parts = parseLocalDate(date);
  return parts
    ? zonedIso({ ...parts, hour: 23, minute: 59, second: 59 }, timeZone, "999999")
    : null;
}

/** Local calendar date `YYYY-MM-DD` of `now` in `timeZone`. */
export function todayInTimezone(timeZone: string, now: Date = new Date()): string {
  const p = zonedParts(now, timeZone);
  return `${pad(p.year, 4)}-${pad(p.month)}-${pad(p.day)}`;
}

/** Local calendar month `YYYY-MM` of `now` in `timeZone`. */
export function currentMonth(timeZone: string, now: Date = new Date()): string {
  return todayInTimezone(timeZone, now).slice(0, 7);
}
