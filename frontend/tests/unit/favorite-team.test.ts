import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  getFavoriteTeam,
  setFavoriteTeam,
  useFavoriteTeam,
} from "@/lib/favoriteTeam";
import { act, renderHook } from "@testing-library/react";

const KEY = "rosterlab.favoriteTeam";

beforeEach(() => {
  window.localStorage.clear();
  setFavoriteTeam(null);
});

describe("the favourite-team store", () => {
  it("round-trips a team", () => {
    setFavoriteTeam({ id: "t1", abbreviation: "BOS" });
    expect(getFavoriteTeam()).toEqual({ id: "t1", abbreviation: "BOS" });
  });

  it("clears to null rather than to an empty team", () => {
    setFavoriteTeam({ id: "t1", abbreviation: "BOS" });
    setFavoriteTeam(null);
    expect(getFavoriteTeam()).toBeNull();
    expect(window.localStorage.getItem(KEY)).toBeNull();
  });

  it("returns a stable object identity while the stored value is unchanged", () => {
    // `getSnapshot` runs on every render. A freshly parsed object each time gives
    // consumers a new identity every render, and an effect keyed on it never settles.
    setFavoriteTeam({ id: "t1", abbreviation: "BOS" });
    expect(getFavoriteTeam()).toBe(getFavoriteTeam());
  });

  it("treats a malformed entry as no favourite instead of throwing", () => {
    window.localStorage.setItem(KEY, "{not json");
    expect(getFavoriteTeam()).toBeNull();
    window.localStorage.setItem(KEY, JSON.stringify({ id: 7 }));
    expect(getFavoriteTeam()).toBeNull();
  });

  it("survives storage being unavailable", () => {
    // Safari private mode and disabled-cookie profiles throw here. An uncaught throw
    // inside `getSnapshot` takes the whole page down.
    const store = window.localStorage;
    const getItem = vi.spyOn(store, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    const setItem = vi.spyOn(store, "setItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    try {
      expect(() => setFavoriteTeam({ id: "t1", abbreviation: "BOS" })).not.toThrow();
      expect(getFavoriteTeam()).toBeNull();
    } finally {
      getItem.mockRestore();
      setItem.mockRestore();
    }
  });

  it("re-renders a subscriber when THIS tab writes", () => {
    const { result } = renderHook(() => useFavoriteTeam());
    expect(result.current).toBeNull();
    act(() => setFavoriteTeam({ id: "t1", abbreviation: "BOS" }));
    expect(result.current).toEqual({ id: "t1", abbreviation: "BOS" });
  });

  it("re-renders a subscriber when ANOTHER tab writes", () => {
    // The R7 defect. `storage` fires only in the tabs that did not write, so without a
    // listener two open tabs disagreed until one was reloaded — a background tab kept
    // showing the previous team's colours and deep-linking to it.
    const { result } = renderHook(() => useFavoriteTeam());
    act(() => {
      window.localStorage.setItem(KEY, JSON.stringify({ id: "t9", abbreviation: "LAL" }));
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: KEY,
          newValue: JSON.stringify({ id: "t9", abbreviation: "LAL" }),
        }),
      );
    });
    expect(result.current).toEqual({ id: "t9", abbreviation: "LAL" });
  });

  it("reacts to another tab clearing all storage", () => {
    setFavoriteTeam({ id: "t1", abbreviation: "BOS" });
    const { result } = renderHook(() => useFavoriteTeam());
    expect(result.current).not.toBeNull();
    act(() => {
      window.localStorage.clear();
      window.dispatchEvent(new StorageEvent("storage", { key: null }));
    });
    expect(result.current).toBeNull();
  });

  it("ignores a storage event for an unrelated key", () => {
    setFavoriteTeam({ id: "t1", abbreviation: "BOS" });
    const { result } = renderHook(() => useFavoriteTeam());
    const before = result.current;
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "something.else" }));
    });
    expect(result.current).toBe(before);
  });
});
