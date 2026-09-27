// Minimalny współdzielony stan aplikacji z powiadamianiem subskrybentów.

export function createStore(initial) {
  let state = { ...initial };
  const listeners = new Set();
  return {
    get: () => state,
    set(patch) {
      const prev = state;
      state = { ...state, ...patch };
      for (const listener of Array.from(listeners)) {
        try {
          listener(state, prev);
        } catch (err) {
          console.error('Błąd subskrybenta stanu:', err);
        }
      }
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

/** Stan asystenta widoczny w UI: bez połączenia zawsze „offline”. */
export function assistantState(s) {
  return s.connected ? s.serverState || 'idle' : 'offline';
}

/** Część „voice” statusu z /api/status (pusty obiekt, gdy brak danych). */
export function voiceInfo(s) {
  return (s.status && s.status.voice) || {};
}

export function isMuted(s) {
  return s.serverState === 'muted' || voiceInfo(s).muted === true;
}
