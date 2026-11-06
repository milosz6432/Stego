import { describe, it, expect } from "vitest";
import { humanSize, rangeQuery, formatHz } from "./format";

describe("humanSize", () => {
  it("formats bytes", () => expect(humanSize(512)).toBe("512 B"));
  it("formats KB", () => expect(humanSize(2048)).toBe("2.0 KB"));
  it("formats MB", () => expect(humanSize(5 * 1024 * 1024)).toBe("5.0 MB"));
  it("formats GB", () => expect(humanSize(3 * 1024 ** 3)).toBe("3.00 GB"));
});

describe("rangeQuery", () => {
  it("empty when no range", () => expect(rangeQuery()).toBe(""));
  it("start only", () => expect(rangeQuery(1.5)).toBe("&start=1.5"));
  it("start and end", () => expect(rangeQuery(1, 2)).toBe("&start=1&end=2"));
  it("allows zero start", () => expect(rangeQuery(0, 5)).toBe("&start=0&end=5"));
});

describe("formatHz", () => {
  it("hz below 1k", () => expect(formatHz(440)).toBe("440.0 Hz"));
  it("khz above 1k", () => expect(formatHz(1500)).toBe("1.50 kHz"));
});
