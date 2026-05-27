export function isDebugUiEnabled() {
  if (typeof window === "undefined") {
    return false;
  }
  const params = new URLSearchParams(window.location.search);
  const queryValue = params.get("debug");
  if (queryValue === "1" || queryValue === "true") {
    return true;
  }
  try {
    return window.localStorage.getItem("cs-kb-debug") === "1";
  } catch {
    return false;
  }
}
