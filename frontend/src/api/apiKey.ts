/**
 * Browser-side API key storage (docs/frontend-architecture.md §8, SD-017).
 *
 * The operator issues a dedicated read-only UI identity (e.g. `UI01:<key>`
 * in the backend `API_KEYS`); the key is entered once in Settings and kept
 * in localStorage. A change event keeps React subscribers in sync.
 */

const STORAGE_KEY = "observatory.api-key";
const CHANGE_EVENT = "observatory:api-key-changed";

export function getApiKey(): string | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value && value.length > 0 ? value : null;
  } catch {
    // localStorage can be unavailable (privacy mode); treat as "no key".
    return null;
  }
}

export function setApiKey(key: string | null): void {
  try {
    if (key && key.length > 0) {
      window.localStorage.setItem(STORAGE_KEY, key);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // Ignore storage failures; the key just won't persist.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** Subscribe to key changes (same tab via custom event, other tabs via storage). */
export function subscribeApiKey(callback: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(CHANGE_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}
