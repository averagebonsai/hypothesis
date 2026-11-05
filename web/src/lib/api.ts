/**
 * API configuration helper for Hypothesis web application.
 * Dynamically resolves API endpoints across local development and production (e.g. Render).
 */

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") || "http://localhost:8000"
);

/**
 * Returns a fully qualified API URL for a given relative path.
 * @param path - e.g. "/api/presets" or "api/presets"
 */
export function apiUrl(path: string): string {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${cleanPath}`;
}
