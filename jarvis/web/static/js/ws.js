// Klient WebSocket z automatycznym wznawianiem połączenia i prostym emiterem zdarzeń.
//
// Wiadomości serwera {topic, data, ts} są emitowane pod nazwą tematu: handler(data, message).
// Zdarzenia lokalne: 'socket:open', 'socket:close', 'socket:message'.

export class Emitter {
  constructor() {
    this._handlers = new Map();
  }

  /** Rejestruje handler; zwraca funkcję wyrejestrowującą. */
  on(topic, handler) {
    if (!this._handlers.has(topic)) this._handlers.set(topic, new Set());
    this._handlers.get(topic).add(handler);
    return () => this.off(topic, handler);
  }

  off(topic, handler) {
    const set = this._handlers.get(topic);
    if (set) set.delete(handler);
  }

  emit(topic, ...args) {
    const set = this._handlers.get(topic);
    if (!set) return;
    for (const handler of Array.from(set)) {
      try {
        handler(...args);
      } catch (err) {
        console.error(`Błąd w obsłudze zdarzenia „${topic}”:`, err);
      }
    }
  }
}

export class JarvisSocket extends Emitter {
  constructor(url, { minDelay = 500, maxDelay = 5000 } = {}) {
    super();
    this.url = url;
    this.minDelay = minDelay;
    this.maxDelay = maxDelay;
    this.delay = minDelay;
    this.ws = null;
    this.timer = 0;
    this.connected = false;
  }

  connect() {
    clearTimeout(this.timer);
    this.timer = 0;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;

    let ws;
    try {
      ws = new WebSocket(this.url);
    } catch (err) {
      console.warn('Nie można otworzyć WebSocket:', err);
      this._scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      if (ws !== this.ws) return;
      this.connected = true;
      this.delay = this.minDelay;
      this.emit('socket:open');
    };
    ws.onmessage = (event) => {
      if (ws === this.ws) this._handleMessage(event.data);
    };
    ws.onclose = () => {
      if (ws !== this.ws) return;
      const wasConnected = this.connected;
      this.ws = null;
      this.connected = false;
      this.emit('socket:close', { wasConnected });
      this._scheduleReconnect();
    };
    ws.onerror = () => {
      // Po błędzie zawsze przychodzi „close” – tam wznawiamy połączenie.
    };
  }

  /** Natychmiastowa próba połączenia (np. po powrocie sieci lub odsłonięciu okna). */
  reconnectNow() {
    if (this.connected || (this.ws && this.ws.readyState === WebSocket.CONNECTING)) return;
    this.delay = this.minDelay;
    this.connect();
  }

  /** Wysyła obiekt jako JSON. Zwraca false, gdy nie ma połączenia. */
  send(payload) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    try {
      this.ws.send(JSON.stringify(payload));
      return true;
    } catch (err) {
      console.warn('Nie udało się wysłać wiadomości:', err);
      return false;
    }
  }

  _scheduleReconnect() {
    if (this.timer) return;
    const delay = this.delay;
    this.delay = Math.min(this.delay * 2, this.maxDelay);
    this.timer = setTimeout(() => {
      this.timer = 0;
      this.connect();
    }, delay);
  }

  _handleMessage(raw) {
    let message;
    try {
      message = JSON.parse(raw);
    } catch {
      console.warn('Niepoprawny JSON z serwera:', raw);
      return;
    }
    if (!message || typeof message.topic !== 'string') return;
    const data = message.data && typeof message.data === 'object' ? message.data : {};
    this.emit(message.topic, data, message);
    this.emit('socket:message', message);
  }
}
