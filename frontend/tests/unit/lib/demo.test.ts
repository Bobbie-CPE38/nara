import { describe, expect, it } from "vitest";
import { formatDemoTime } from "@/lib/demo";

describe("formatDemoTime", () => {
  it("shows missing timestamps as a dash", () => {
    expect(formatDemoTime(null)).toBe("—");
  });
  it.each(["", "not-a-date"])(
    "preserves malformed timestamp %j without throwing",
    (value) => {
      expect(formatDemoTime(value)).toBe(value);
    },
  );
  it("uses the shared Bangkok format", () => {
    expect(formatDemoTime("2026-10-09T14:00:00Z")).toBe("2026-10-09 21:00:00");
  });
});
