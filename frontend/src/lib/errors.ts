import { ApiError } from "@/lib/api";
import type { Translate } from "@/lib/i18n";

/**
 * An error as the user reads it (round 6 PR UI2, docs/workflow.md 6.32). The words the API
 * sent stay as they are; the texts the frontend made itself (the API answered without
 * details, the server cannot be reached, a read took too long, an answer of an unexpected
 * shape) are in the language of the page.
 */
export function describeError(error: unknown, t: Translate): string {
  if (error instanceof ApiError) {
    // ApiError makes this text when the body has no detail of its own
    return error.message === `API request failed (${error.status})`
      ? t("common.apiFailed", { status: error.status })
      : error.message;
  }
  // fetch reports an unreachable server as a TypeError with a browser-specific text
  if (error instanceof TypeError) return t("common.apiUnreachable");
  if (error instanceof Error) {
    const timeout = /^Polling request timed out after (\d+) ms$/.exec(error.message);
    if (timeout) return t("common.pollTimeout", { ms: timeout[1] });
    if (error.message === "Unexpected response from the API") return t("common.unexpectedResponse");
    return error.message;
  }
  return String(error);
}
