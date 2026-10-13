const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const msg =
      data?.error?.message ||
      data?.detail ||
      (typeof data === "string" ? data : null) ||
      `Request failed (${res.status})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

export const api = {
  get: (path) => request(path),
  post: (path, body) =>
    request(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: (path, body) => request(path, { method: "PUT", body: JSON.stringify(body) }),
  postForm: (path, formData) =>
    request(path, { method: "POST", headers: {}, body: formData }),
};

export { API_BASE };
