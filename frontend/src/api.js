// Everything that talks to the backend goes through here.
const read = (k) => {
  try { return localStorage.getItem(k) || ""; } catch (_) { return ""; }
};

export function getApiBase() {
  const url =
    read("fw_api") ||
    (window.FW_CONFIG && window.FW_CONFIG.apiUrl) ||
    import.meta.env.VITE_API_URL ||
    `${location.protocol}//${location.hostname}:8000`;
  return url.replace(/\/+$/, "");
}
export const getKey = () => read("fw_key");

export function saveConnection(apiUrl, key) {
  try {
    localStorage.setItem("fw_api", apiUrl.trim());
    localStorage.setItem("fw_key", key.trim());
  } catch (_) {}
}

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

export async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const key = getKey();
  if (key) headers["X-API-Key"] = key;
  let r;
  try {
    r = await fetch(getApiBase() + path, { ...opts, headers });
  } catch (_) {
    throw new ApiError("Cannot reach the backend.", 0);
  }
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) {}
    throw new ApiError(msg, r.status);
  }
  return r.json();
}

export const sendJson = (path, body, method = "POST") =>
  api(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

// URL for <img src> and download links (they cannot send headers, so the key goes in the address).
export function assetUrl(path) {
  const key = getKey();
  const url = getApiBase() + path;
  return key ? `${url}${url.includes("?") ? "&" : "?"}key=${encodeURIComponent(key)}` : url;
}

export function wsUrl() {
  const key = getKey();
  return getApiBase().replace(/^http/, "ws") + "/ws" + (key ? `?key=${encodeURIComponent(key)}` : "");
}
