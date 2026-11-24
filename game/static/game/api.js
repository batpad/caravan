// Thin client for the Django JSON API + per-game seat token storage.

const KEY = (code) => `caravan:${code.toUpperCase()}`;

export const seats = {
  get(code) {
    try { return JSON.parse(localStorage.getItem(KEY(code))) || null; } catch { return null; }
  },
  set(code, data) {
    try { localStorage.setItem(KEY(code), JSON.stringify(data)); } catch { /* private mode */ }
  },
  clear(code) {
    try { localStorage.removeItem(KEY(code)); } catch { /* ignore */ }
  },
};

async function request(method, url, body, code) {
  const headers = { "Content-Type": "application/json" };
  const seat = code && seats.get(code);
  if (seat) headers["X-Seat-Token"] = seat.token;
  const res = await fetch(url, { method, headers, body: body ? JSON.stringify(body) : undefined });
  let data = {};
  try { data = await res.json(); } catch { /* empty */ }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

export const api = {
  staticInfo: () => request("GET", "/api/static/"),
  listGames: () => request("GET", "/api/games/"),
  createGame: (player, name, maxPlayers) =>
    request("POST", "/api/games/", { player, name, max_players: maxPlayers }),
  join: (code, player) => request("POST", `/api/games/${code}/join/`, { player }),
  leave: (code) => request("POST", `/api/games/${code}/leave/`, {}, code),
  createVsBots: (player, bots, level) =>
    request("POST", "/api/games/", { player, bots, bot_level: level }),
  createTutorial: (player) => request("POST", "/api/games/", { player, tutorial: true }),
  addBot: (code, level) => request("POST", `/api/games/${code}/add_bot/`, level ? { level } : {}, code),
  removeSeat: (code, index) => request("POST", `/api/games/${code}/remove_seat/`, { index }, code),
  hint: (code) => request("GET", `/api/games/${code}/hint/`, null, code),
  start: (code) => request("POST", `/api/games/${code}/start/`, {}, code),
  state: (code, since) =>
    request("GET", `/api/games/${code}/state/${since != null ? `?since=${since}` : ""}`, null, code),
  act: (code, action) => request("POST", `/api/games/${code}/action/`, action, code),
};
