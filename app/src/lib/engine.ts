// WebSocket client for the local Python engine (127.0.0.1 only, token-authenticated).
type Listener = (msg: any) => void;

export class EngineClient {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private retry = 0;
  private closed = false;
  connected = false;

  on(fn: Listener) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(msg: any) {
    this.listeners.forEach((fn) => fn(msg));
  }

  async connect() {
    this.closed = false;
    const info = await window.agent?.engineInfo();
    if (!info) {
      this.emit({ type: "_engine_down" });
      this.scheduleReconnect();
      return;
    }
    const ws = new WebSocket(`ws://127.0.0.1:${info.port}`);
    this.ws = ws;
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "auth", token: info.token }));
      this.retry = 0;
      this.connected = true;
      this.emit({ type: "_connected" });
    };
    ws.onmessage = (ev) => {
      try {
        this.emit(JSON.parse(ev.data));
      } catch {
        /* ignore malformed */
      }
    };
    ws.onclose = () => {
      this.connected = false;
      this.emit({ type: "_disconnected" });
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect() {
    if (this.closed) return;
    const delay = Math.min(5000, 500 * 2 ** this.retry++);
    setTimeout(() => this.connect(), delay);
  }

  send(msg: Record<string, unknown>) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  close() {
    this.closed = true;
    this.ws?.close();
  }
}

export const engine = new EngineClient();
