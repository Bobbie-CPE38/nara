import { ApiError, ApiUnreachableError } from "@/lib/api";
import type { Translate } from "@/lib/i18n";

/** A read that took longer than its limit (usePolling). */
export class PollTimeoutError extends Error {
  constructor(public readonly timeoutMs: number) {
    super(`Polling request timed out after ${timeoutMs} ms`);
    this.name = "PollTimeoutError";
  }
}

/** The API answered with a shape the page does not know (lib/cases.ts). */
export class UnexpectedResponseError extends Error {
  constructor() {
    super("Unexpected response from the API");
    this.name = "UnexpectedResponseError";
  }
}

/**
 * An error as the user reads it (round 6 PR UI2, docs/workflow.md 6.32). The words the API
 * sent stay as they are; the texts the frontend made itself (the API answered without
 * details, the server cannot be reached, a read took too long, an answer of an unexpected
 * shape) are in the language of the page. Call it when the page renders, not when the error
 * happens, so a switch of language also changes the error on the screen.
 */
export function describeError(error: unknown, t: Translate): string {
  if (error instanceof ApiError) {
    return error.hasDetail ? error.message : t("common.apiFailed", { status: error.status });
  }
  if (error instanceof ApiUnreachableError) return t("common.apiUnreachable");
  if (error instanceof PollTimeoutError) return t("common.pollTimeout", { ms: error.timeoutMs });
  if (error instanceof UnexpectedResponseError) return t("common.unexpectedResponse");
  // Anything else is a fault of our own code: show what it says, not "cannot reach the server"
  if (error instanceof Error) return error.message;
  return String(error);
}
