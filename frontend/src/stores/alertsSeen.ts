/** Tracks when the user last opened the Alert Center, to compute the unread
 *  notification badge in the header. Persisted per browser. */
const STORAGE_KEY = "rack-insight-alerts-seen-at";

export function getAlertsSeenAt(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function markAlertsSeen(): void {
  try {
    localStorage.setItem(STORAGE_KEY, new Date().toISOString());
  } catch {
    // ignore storage failures
  }
}

export function countUnread(createdAts: string[]): number {
  const seenAt = getAlertsSeenAt();
  if (!seenAt) return createdAts.length;
  const seen = new Date(seenAt).getTime();
  return createdAts.filter((t) => new Date(t).getTime() > seen).length;
}
