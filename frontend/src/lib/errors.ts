import { ApiError, ApiUnreachableError, authCode } from "@/lib/api";
import type { MessageKey, Translate } from "@/lib/i18n";

/** The codes of the login API (docs/workflow.md 6.33.3) and the sentence of each, in the user's language. */
const AUTH_MESSAGES: Record<string, MessageKey> = {
  AUTH_REQUIRED: "auth.err.required",
  AUTH_FORBIDDEN: "auth.err.forbidden",
  AUTH_INVALID_CREDENTIALS: "auth.err.invalidCredentials",
  AUTH_INVALID_PASSWORD: "auth.err.invalidPassword",
  AUTH_INVALID_REGISTRATION: "auth.err.invalidRegistration",
  AUTH_RATE_LIMITED: "auth.err.rateLimited",
  AUTH_ORIGIN_FORBIDDEN: "auth.err.origin",
  AUTH_PASSWORD_CHANGE_REQUIRED: "auth.err.changeRequired",
};

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
    // A code of the login API is not a sentence for a person: the page words it itself
    const code = authCode(error);
    if (code !== undefined && code in AUTH_MESSAGES) return t(AUTH_MESSAGES[code]);
    return error.hasDetail ? error.message : t("common.apiFailed", { status: error.status });
  }
  if (error instanceof ApiUnreachableError) return t("common.apiUnreachable");
  if (error instanceof PollTimeoutError) return t("common.pollTimeout", { ms: error.timeoutMs });
  if (error instanceof UnexpectedResponseError) return t("common.unexpectedResponse");
  // Anything else is a fault of our own code: show what it says, not "cannot reach the server"
  if (error instanceof Error) return error.message;
  return String(error);
}
