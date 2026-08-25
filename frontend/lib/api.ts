import type { ZodType } from "zod";

const BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }

  /**
   * The server's message, with no class-name prefix.
   *
   * Error pages interpolate `String(error)`, and the default `Error.prototype.toString`
   * produced user-facing copy like "Could not load player: **Error:** player
   * not-a-real-player-id not found".
   */
  override toString(): string {
    return this.message;
  }
}

/**
 * `schema` is optional and applied only to the responses that carry decision numbers
 * (see lib/schemas.ts). Without it this returns a bare cast, which is what let a
 * backend shape change render `undefined` on screen instead of failing.
 */
async function request<T>(path: string, init?: RequestInit, schema?: ZodType): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let code = "http_error";
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code, message);
  }
  const payload = await res.json();
  if (schema) {
    const parsed = schema.safeParse(payload);
    if (!parsed.success) {
      const first = parsed.error.issues[0];
      throw new ApiError(
        502,
        "contract_mismatch",
        `The server returned an unexpected shape for ${path}` +
          (first ? ` (${first.path.join(".") || "root"}: ${first.message})` : "") +
          ". This is a bug, not a data gap — the response was not rendered.",
      );
    }
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string, schema?: ZodType) => request<T>(path, undefined, schema),
  post: <T>(path: string, body: unknown, schema?: ZodType) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }, schema),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
};
