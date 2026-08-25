import "@testing-library/jest-dom/vitest";

/**
 * A real `localStorage` for the unit environment.
 *
 * This vitest/jsdom build exposes `window.localStorage` as a **plain empty object** — no
 * `getItem`, no `setItem`, no `clear`. Anything touching it throws `TypeError: getItem is
 * not a function`, which is why nothing that persists across a page load had a unit test
 * before R7: the favourite-team store silently did nothing here and the tests that would
 * have caught the missing cross-tab listener could not have been written.
 *
 * `StorageEvent` itself is present, so only the store needs supplying. Each backing map is
 * per-test-file, which is the isolation a shared browser origin would not give.
 */
class MemoryStorage implements Storage {
  private entries = new Map<string, string>();

  get length(): number {
    return this.entries.size;
  }

  key(index: number): string | null {
    return [...this.entries.keys()][index] ?? null;
  }

  getItem(key: string): string | null {
    return this.entries.has(key) ? (this.entries.get(key) as string) : null;
  }

  setItem(key: string, value: string): void {
    this.entries.set(String(key), String(value));
  }

  removeItem(key: string): void {
    this.entries.delete(key);
  }

  clear(): void {
    this.entries.clear();
  }

  [name: string]: unknown;
}

// Defined unconditionally, and before anything reads the property. Node 25 ships its own
// experimental Web Storage, and merely *touching* `window.localStorage` initialises it and
// prints `Warning: --localstorage-file was provided without a valid path` on every worker.
// Shadowing it without probing it keeps the test output clean and keeps the backing store
// in memory where a test can reason about it.
for (const name of ["localStorage", "sessionStorage"] as const) {
  Object.defineProperty(window, name, {
    value: new MemoryStorage(),
    configurable: true,
    writable: true,
  });
}
