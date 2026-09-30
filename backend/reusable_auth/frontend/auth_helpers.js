/**
 * Reusable auth helpers for any React app.
 *
 * Usage:
 *   import { getStoredToken, getStoredUser, authFetch, clearAuth } from './auth_helpers';
 *
 * Customise the STORAGE_PREFIX if you want project-specific keys:
 *   localStorage keys will be  `${STORAGE_PREFIX}_token`  and  `${STORAGE_PREFIX}_user`
 */

const STORAGE_PREFIX = 'app'; // change per project (e.g. 'vigilinx', 'myapp')

export function getStoredToken() {
  return localStorage.getItem(`${STORAGE_PREFIX}_token`);
}

export function setStoredToken(token) {
  localStorage.setItem(`${STORAGE_PREFIX}_token`, token);
}

export function getStoredUser() {
  try {
    const raw = localStorage.getItem(`${STORAGE_PREFIX}_user`);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setStoredUser(user) {
  localStorage.setItem(`${STORAGE_PREFIX}_user`, JSON.stringify(user));
}

export function clearAuth() {
  localStorage.removeItem(`${STORAGE_PREFIX}_token`);
  localStorage.removeItem(`${STORAGE_PREFIX}_user`);
}

/**
 * Wrapper around fetch() that injects the JWT Bearer header automatically.
 */
export function authFetch(url, options = {}) {
  const token = getStoredToken();
  const headers = { ...(options.headers || {}) };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return fetch(url, { ...options, headers });
}

/**
 * Call this after a successful /api/auth/login response.
 * Stores token + user in localStorage and returns { token, user }.
 */
export function handleLoginResponse(data) {
  setStoredToken(data.token);
  setStoredUser(data.user);
  return { token: data.token, user: data.user };
}
