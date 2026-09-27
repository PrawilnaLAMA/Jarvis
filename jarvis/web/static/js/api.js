// Wywołania REST backendu. Ścieżki są względne, więc działają niezależnie od hosta i portu.

const TIMEOUT_MS = 12000;

/** Błąd API z komunikatem po polsku; `errors` to lista szczegółów (np. walidacji ustawień). */
export class ApiError extends Error {
  constructor(message, { status = 0, errors = [], data = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.errors = errors;
    this.data = data;
  }
}

export async function request(method, path, body) {
  const controller = typeof AbortController === 'function' ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), TIMEOUT_MS) : 0;
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let response;
  let text = '';
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: 'no-store',
      signal: controller ? controller.signal : undefined,
    });
    text = response.status === 204 ? '' : await response.text();
  } catch (err) {
    const aborted = err && err.name === 'AbortError';
    throw new ApiError(aborted ? 'Serwer nie odpowiada.' : 'Brak połączenia z serwerem.');
  } finally {
    clearTimeout(timer);
  }

  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    throw new ApiError(errorMessage(response.status, data), {
      status: response.status,
      errors: errorList(data),
      data,
    });
  }
  return data;
}

function errorMessage(status, data) {
  const detail = data && data.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) return 'Nieprawidłowe dane.'; // walidacja FastAPI (422)
  if (status === 404) return 'Nie znaleziono (404).';
  if (status === 405 || status === 501) return 'Ta funkcja nie jest dostępna w backendzie.';
  if (status >= 500) return `Błąd serwera (${status}).`;
  return `Błąd żądania (${status}).`;
}

function errorList(data) {
  if (!data) return [];
  if (Array.isArray(data.errors)) return data.errors.map(String);
  if (Array.isArray(data.detail)) {
    return data.detail.map((item) => {
      if (item && item.msg) {
        const loc = Array.isArray(item.loc) ? item.loc.filter((p) => p !== 'body').join('.') : '';
        return loc ? `${loc}: ${item.msg}` : item.msg;
      }
      return String(item);
    });
  }
  return [];
}

const enc = encodeURIComponent;

export const api = {
  status: () => request('GET', 'api/status'),
  command: (text) => request('POST', 'api/command', { text }),

  events: () => request('GET', 'api/calendar/events'),
  occurrences: (start, end) => request('GET', `api/calendar/occurrences?start=${enc(start)}&end=${enc(end)}`),
  createEvent: (event) => request('POST', 'api/calendar/events', event),
  updateEvent: (id, event) => request('PUT', `api/calendar/events/${enc(id)}`, event),
  deleteEvent: (id) => request('DELETE', `api/calendar/events/${enc(id)}`),

  settings: () => request('GET', 'api/settings'),
  saveSettings: (patch) => request('PUT', 'api/settings', patch),
  saveSecrets: (secrets) => request('PUT', 'api/secrets', secrets),

  llmModels: () => request('GET', 'api/llm/models'),
  ttsVoices: () => request('GET', 'api/tts/voices'),
  ttsPreview: (voice, rate, pitch) => request('POST', 'api/tts/preview', { voice, rate, pitch }),
  audioDevices: () => request('GET', 'api/audio/devices'),
};
