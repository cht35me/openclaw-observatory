import { describe, expect, it } from "vitest";

import {
  formatBytes,
  formatEpochRelative,
  formatInstalledMemory,
  formatPercent,
  formatRelativeTime,
  formatUptime,
} from "./format";

describe("formatBytes", () => {
  it("uses binary prefixes like the /monitor page", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(62_192_091_136)).toBe("57.9 GiB");
    expect(formatBytes(41_305_759_744)).toBe("38.5 GiB");
  });

  it("renders a dash for absent or invalid values", () => {
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(undefined)).toBe("—");
    expect(formatBytes(-1)).toBe("—");
    expect(formatBytes(Number.NaN)).toBe("—");
  });
});

describe("formatInstalledMemory", () => {
  it("recovers the marketed module size from MemTotal", () => {
    expect(formatInstalledMemory(3_980_185_600)).toBe("4 GB");
    expect(formatInstalledMemory(8_202_936_320)).toBe("8 GB");
  });

  it("falls back below 1 GB and dashes invalid input", () => {
    expect(formatInstalledMemory(536_870_912)).toBe("512.0 MiB");
    expect(formatInstalledMemory(null)).toBe("—");
  });
});

describe("formatPercent", () => {
  it("keeps one decimal", () => {
    expect(formatPercent(31.84)).toBe("31.8%");
    expect(formatPercent(0)).toBe("0.0%");
    expect(formatPercent(null)).toBe("—");
  });
});

describe("formatEpochRelative", () => {
  it("formats a Unix epoch relative to now", () => {
    const now = new Date("2026-07-22T08:00:00Z");
    const epoch = new Date("2026-07-22T06:00:00Z").getTime() / 1000;
    expect(formatEpochRelative(epoch, now)).toBe("2h ago");
    expect(formatEpochRelative(null, now)).toBe("—");
  });
});

describe("existing helpers stay stable", () => {
  it("formatUptime", () => {
    expect(formatUptime(93_784)).toBe("1d 2h");
    expect(formatUptime(59)).toBe("59s");
  });

  it("formatRelativeTime", () => {
    const now = new Date("2026-07-22T08:00:00Z");
    expect(formatRelativeTime("2026-07-22T07:59:18Z", now)).toBe("42s ago");
    expect(formatRelativeTime("not-a-date", now)).toBe("—");
  });
});
