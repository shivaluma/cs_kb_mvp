import { API_BASE_URL } from "@/config";

async function withTimeout<T>(request: (signal: AbortSignal) => Promise<T>, timeoutMs = 15000) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await request(controller.signal);
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await withTimeout((signal) => fetch(`${API_BASE_URL}${path}`, { signal }));
  if (!response.ok) {
    throw new Error(`GET ${path} failed`);
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T = unknown>(
  path: string,
  payload: unknown,
  timeoutMs = 15000,
): Promise<T> {
  const response = await withTimeout((signal) =>
    fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    }),
    timeoutMs,
  );
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`POST ${path} failed (${response.status})${detail ? `: ${detail}` : ""}`);
  }
  return response.json() as Promise<T>;
}

export async function apiPatch<T = unknown>(
  path: string,
  payload: unknown,
): Promise<T> {
  const response = await withTimeout((signal) =>
    fetch(`${API_BASE_URL}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    }),
  );
  if (!response.ok) {
    throw new Error(`PATCH ${path} failed`);
  }
  return response.json() as Promise<T>;
}

export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const response = await withTimeout(
    (signal) =>
      fetch(`${API_BASE_URL}${path}`, {
        method: "POST",
        body: form,
        signal,
      }),
    120000,
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}
