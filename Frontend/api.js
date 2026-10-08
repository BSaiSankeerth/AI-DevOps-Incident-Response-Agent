// Small fetch wrapper: adds the login token and turns errors into readable messages.
const TOKEN_KEY = 'devops_ai_token';

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

let unauthorizedHandler = () => {};
export function onUnauthorized(handler) {
    unauthorizedHandler = handler;
}

function errorMessage(payload, status) {
    const detail = payload.detail;
    if (Array.isArray(detail)) {
        return detail.map((e) => `${e.loc?.slice(-1)[0] ?? 'input'}: ${e.msg}`).join('; ');
    }
    return detail || payload.message || `Request failed (${status})`;
}

export async function api(path, { method = 'GET', json, form } = {}) {
    const headers = {};
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    let body;
    if (json !== undefined) {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify(json);
    } else if (form) {
        body = form;
    }

    const response = await fetch(`/api${path}`, { method, headers, body });
    const payload = await response.json().catch(() => ({}));

    if (response.status === 401 && token) {
        clearToken();
        unauthorizedHandler(); // session expired -> back to the login page
    }
    if (!response.ok) throw new Error(errorMessage(payload, response.status));
    return payload;
}