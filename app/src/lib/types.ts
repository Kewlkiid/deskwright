export type Box = [number, number, number, number];

export interface AgentBridge {
  platform: string;
  engineInfo(): Promise<{ port: number; token: string } | null>;
  restartEngine(): Promise<{ port: number; token: string } | null>;
  permissions(): Promise<Permissions>;
  revokePermission(kind: PermissionKind): Promise<boolean>;
  askAccessibility(): Promise<boolean>;
  askMicrophone(): Promise<boolean>;
  openPermission(kind: PermissionKind): void;
  setMode(mode: "panel" | "pill" | "mini"): void;
  setRunning(running: boolean): void;
  suppressEsc(): void;
  overlay(evt: Record<string, unknown>): void;
  yieldFocus(): void;
  hideForCapture(): Promise<boolean>;
  showAfterCapture(): void;
  revealFile(file: string): void;
  quit(): void;
  relaunch(): void;
  askScreen(): Promise<boolean>;
  onGlobalStop(cb: () => void): () => void;
  onBounds(cb: (b: { x: number; y: number; width: number; height: number }) => void): () => void;
  onEngineExit(cb: (code: number) => void): () => void;
}

export type PermissionKind = "screen" | "accessibility" | "microphone" | "speech" | "input" | "automation";

export interface Permissions {
  platform: string;
  screen: string;
  restart?: boolean; // Screen Recording was granted while Agent was running: a restart puts it into effect
  microphone: string;
  accessibility: boolean;
  speech?: string; // Speech Recognition, for the wake word: "granted" | "denied" | "not asked" | ...
  input?: boolean | null; // Input Monitoring, for teach mode
}

declare global {
  interface Window {
    agent?: AgentBridge;
  }
}

export interface Metrics {
  steps: number;
  model_calls: number;
  calls_by_role: Record<string, number>;
  cost: number;
  elapsed: number;
  model_time: number;
  cache_hits: number;
  cache_misses: number;
  cache_hit_rate: number;
  calls_saved: number;
  time_saved: number;
  cost_saved: number;
  fixes: number;
  fixes_succeeded: number;
}

export type LineState = "pending" | "running" | "passed" | "failed" | "superseded";

export interface Segment {
  id: number;
  lines: string[];
  states: LineState[];
  expects: Record<number, { text: string; ok: boolean; observation?: string }>;
  cached: Record<number, boolean>;
  failedLine?: number;
  failure?: { code: string; message: string; expect?: string; observation?: string };
  explanation?: string;
  fromLine?: number;
  detour?: boolean; // resumed through a learned way back (no model call), not a new repair
}

export interface RunView {
  key: string;
  task: string;
  draft: boolean;
  status: "draft" | "running" | "succeeded" | "failed" | "stopped" | "declined" | "error";
  segments: Segment[];
  metrics?: Metrics;
  progress?: { done: number; total: number };
  checkpoints: string[];
  finalScript?: string;
  taskId?: number | null;
  trace: TraceItem[];
  phase?: string;
  error?: { message?: string } | null;
}

export interface TraceItem {
  target: string;
  thumbnail?: string | null;
  fromCache: boolean;
  verb: string;
}

export interface ResultItem {
  id: string;
  kind: "table" | "markdown";
  title?: string;
  text?: string;
  columns?: string[];
  rows?: (string | number)[][];
}

export interface SavedTask {
  detours?: number; // learned ways back to steps
  id: number;
  name: string;
  description: string;
  script: string;
  source: string;
  updated: number;
  runs: { id: number; status: string; started: number; metrics: Partial<Metrics> }[];
  versions: { id: number; note: string; created: number }[];
}

export interface ElementInfo {
  target: string;
  verb: string;
  thumbnail?: string | null;
  from_cache: boolean;
  expect?: string;
  box: Box;
}

export type ChatItem =
  | { id: string; kind: "user"; text: string; voice?: boolean }
  | { id: string; kind: "agent"; text: string; path?: string; icon?: "save" | "copy" | "sparkle" }
  | { id: string; kind: "reply"; text: string } // a chat answer
  | { id: string; kind: "error"; text: string }
  | { id: string; kind: "run"; runKey: string }
  | { id: string; kind: "result"; result: ResultItem }
  | { id: string; kind: "question"; qid: string; question: string; answer?: string; closed?: boolean }
  | { id: string; kind: "confirm"; qid: string; summary: string; answer?: boolean; closed?: boolean }
  | { id: string; kind: "summary"; runKey: string }
  | { id: string; kind: "tasks" }
  | { id: string; kind: "metrics" }
  | { id: string; kind: "permissions" }
  | {
      id: string;
      kind: "teach";
      name: string;
      description: string;
      script: string;
      steps: { step: number; kind: string; intent?: string; element?: string }[];
      problems: string[];
      saved?: boolean;
    };
