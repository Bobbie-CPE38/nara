const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  /** False when the API sent no sentence of its own and the message is ours. */
  readonly hasDetail: boolean;

  constructor(
    public readonly status: number,
    public readonly body: unknown,
  ) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? body.detail
        : body;
    super(typeof detail === "string" ? detail : `API request failed (${status})`);
    this.hasDetail = typeof detail === "string";
    this.name = "ApiError";
  }
}

/** fetch itself failed: the server cannot be reached (a bug in our own code is not this). */
export class ApiUnreachableError extends Error {
  constructor(public readonly original: unknown) {
    super(original instanceof Error ? original.message : "API is unreachable");
    this.name = "ApiUnreachableError";
  }
}

export type ApiOptions = Omit<RequestInit, "body"> & {
  demoUser?: number;
  json?: unknown;
};

/** Public reads may omit demoUser; user actions must supply their acting staff ID. */
export async function apiRequest<T>(
  path: string,
  { demoUser, json, headers: initialHeaders, ...init }: ApiOptions = {},
): Promise<T> {
  if (!path.startsWith("/") || path.startsWith("//")) {
    throw new Error("API paths must start with a single slash");
  }
  const headers = new Headers(initialHeaders);
  headers.set("Accept", "application/json");
  if (demoUser !== undefined) {
    if (!Number.isSafeInteger(demoUser) || demoUser <= 0) {
      throw new Error("demoUser must be a positive safe integer staff ID");
    }
    headers.set("X-Demo-User", String(demoUser));
  }
  if (json !== undefined) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      body: json === undefined ? undefined : JSON.stringify(json),
      cache: init.cache ?? "no-store",
    });
  } catch (cause) {
    // An abort is the caller's own doing, not a failure of the server
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiUnreachableError(cause);
  }
  const text = await response.text();
  let body: unknown = undefined;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}

/** Bind an identity per screen: 105 for leave, 201 for acceptance, 900 for approval. */
export function createDemoApi(demoUser: number) {
  return <T>(path: string, options: Omit<ApiOptions, "demoUser"> = {}) =>
    apiRequest<T>(path, { ...options, demoUser });
}
