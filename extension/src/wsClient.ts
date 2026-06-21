import WebSocket = require("ws");
import * as vscode from "vscode";
import { notifyWake } from "./notify";

export interface WakeEvent {
  thread_id: string;
  status: string;
  status_reason: string | null;
  baton: string | null;
  last_turn_id: number;
}

export class AgentWakeClient {
  private socket: WebSocket | undefined;
  private reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  private disposed = false;

  public constructor(
    private readonly routerUrl: string,
    private readonly threadId: string,
    private readonly token: string,
    private readonly output: vscode.OutputChannel
  ) {}

  public connect(): void {
    if (this.disposed) {
      return;
    }
    const url = wakeUrl(this.routerUrl, this.threadId);
    this.output.appendLine(`Connecting to ${url}`);
    this.socket = new WebSocket(url, {
      headers: { Authorization: `Bearer ${this.token}`, Origin: "http://127.0.0.1" }
    });
    this.socket.on("message", data => this.onMessage(data));
    this.socket.on("close", code => this.onClose(code));
    this.socket.on("error", err => this.output.appendLine(`WS error: ${err.message}`));
  }

  public dispose(): void {
    this.disposed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    this.socket?.close();
  }

  private onMessage(data: WebSocket.RawData): void {
    try {
      const event = JSON.parse(data.toString()) as WakeEvent;
      void notifyWake(event);
    } catch (err) {
      this.output.appendLine(`Bad wake frame: ${String(err)}`);
    }
  }

  private onClose(code: number): void {
    this.output.appendLine(`WS closed: ${code}`);
    if (!this.disposed) {
      this.reconnectTimer = setTimeout(() => this.connect(), 1000);
    }
  }
}

function wakeUrl(routerUrl: string, threadId: string): string {
  const base = routerUrl.replace(/\/$/, "");
  const path = base.endsWith("/ws") ? base : `${base}/ws`;
  return `${path}?thread_id=${encodeURIComponent(threadId)}`;
}
