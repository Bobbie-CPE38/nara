import { describe, expect, it } from "vitest";
import { ApiError, ApiUnreachableError } from "../../../src/lib/api";
import { describeError, PollTimeoutError, UnexpectedResponseError } from "../../../src/lib/errors";
import { translator } from "../../../src/lib/i18n";

const th = translator("th");
const en = translator("en");

describe("describeError", () => {
  it("keeps the sentence the API sent and gives its own text in the language of the page", () => {
    expect(describeError(new ApiError(409, { detail: "Staff 105 is busy" }), th)).toBe("Staff 105 is busy");
    expect(describeError(new ApiError(500, {}), en)).toBe("API request failed (500)");
    expect(describeError(new ApiError(500, {}), th)).toBe("คำขอไปยัง API ไม่สำเร็จ (500)");
  });

  it("translates the three errors the frontend makes by their type, not by their words", () => {
    expect(describeError(new ApiUnreachableError(new TypeError("Failed to fetch")), th)).toContain("API");
    expect(describeError(new PollTimeoutError(500), th)).toContain("500");
    expect(describeError(new UnexpectedResponseError(), th)).not.toBe("Unexpected response from the API");
    // an error that only has the same words is not one of them
    expect(describeError(new Error("Unexpected response from the API"), th)).toBe("Unexpected response from the API");
  });

  it("does not call a bug in our own code a network failure", () => {
    const bug = new TypeError("Cannot read properties of undefined (reading 'id')");
    expect(describeError(bug, th)).toBe("Cannot read properties of undefined (reading 'id')");
  });
});
