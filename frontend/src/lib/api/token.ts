// Access token chỉ nằm trong bộ nhớ (không localStorage) để giảm rủi ro XSS.
// Refresh token là cookie HttpOnly do backend đặt, JS không đọc được.
let accessToken: string | null = null;
const listeners = new Set<(t: string | null) => void>();

export function getAccessToken() {
  return accessToken;
}

export function setAccessToken(token: string | null) {
  accessToken = token;
  listeners.forEach((l) => l(token));
}

export function onAccessTokenChange(listener: (t: string | null) => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
