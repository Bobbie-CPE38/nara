import { afterEach, describe, expect, it, vi } from "vitest";
import { formatDateTime, formatValue } from "../../../src/lib/format";

afterEach(() => vi.unstubAllEnvs());

describe("formatDateTime", () => {
  it.each([
    ["2026-10-09T21:00:00+07:00", "2026-10-09 21:00:00"],
    ["2026-10-09T14:00:00Z", "2026-10-09 21:00:00"],
    ["2026-10-09T17:30:00Z", "2026-10-10 00:30:00"],
    ["2026-10-09T23:00:00.123456+07:00", "2026-10-09 23:00:00"],
  ])("shows %s as Bangkok time", (iso, expected) => {
    expect(formatDateTime(iso)).toBe(expected);
  });

  it("does not follow the time zone of the machine", () => {
    vi.stubEnv("TZ", "America/New_York");
    expect(new Date("2026-10-09T21:00:00+07:00").getHours()).toBe(10);
    expect(formatDateTime("2026-10-09T21:00:00+07:00")).toBe("2026-10-09 21:00:00");
  });

  it.each(["", "not a time", "2026-13-45T99:00:00+07:00"])("returns the unreadable value %j as it is", value => {
    expect(formatDateTime(value)).toBe(value);
  });
});

describe("formatValue", () => {
  it.each([
    ["STAFF_UNAVAILABLE", "STAFF_UNAVAILABLE"],
    ["", ""],
    [105, "105"],
    [0, "0"],
    [true, "true"],
    [false, "false"],
    [null, "—"],
    [undefined, "—"],
    [[8], "[8]"],
    [[], "[]"],
    [[{ role_id: 1, gap_count: 1 }], '[{"role_id":1,"gap_count":1}]'],
    [{ from: "OPEN" }, '{"from":"OPEN"}'],
  ])("shows %j as %j", (value, expected) => {
    expect(formatValue(value)).toBe(expected);
  });
});
