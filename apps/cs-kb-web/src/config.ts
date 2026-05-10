declare global {
  interface Window {
    __CS_KB_CONFIG__?: {
      API_BASE_URL?: string;
    };
  }
}

export const API_BASE_URL =
  window.__CS_KB_CONFIG__?.API_BASE_URL ??
  import.meta.env.VITE_API_BASE_URL ??
  "http://localhost:8080";
