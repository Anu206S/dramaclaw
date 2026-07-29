// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
// SuperTale project-scoped task endpoints — read task state, subscribe to SSE.
//
// We use native EventSource because SuperTale auth is cookie-based and
// HttpOnly cookies are sent on the EventSource handshake automatically
// (no header needed). If the cookie is missing/expired, the stream returns
// a 401 immediately and we surface that to the caller.

import { apiCall } from "./client";
import { SESSION_EXPIRED_EVENT } from "@/lib/session-expiry";
import { readUrl } from "@/lib/url-params";

export type TaskStatus =
  | "submitting"
  | "queued"
  | "pending"
  | "starting"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface TaskState {
  task_type: string;
  task_key: string;
  project_id?: string;
  username: string;
  project: string;
  episode: number;
  beat_num?: number | null;
  scope?: string | null;
  status: TaskStatus;
  progress?: number | null;
  current_task?: string | null;
  result?: Record<string, unknown> | null;
  error?: string | null;
  logs?: string[];
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, unknown> | null;
}

export type ProjectTaskQueueKind = "default" | "video" | "world" | "ffmpeg";

export interface ProjectTaskLaneLimits {
  limit: number | null;
  active: number;
  remaining: number | null;
  user_limit: number | null;
  user_active: number;
  user_remaining: number | null;
}

export type ProjectTaskLimits = Record<ProjectTaskQueueKind, ProjectTaskLaneLimits>;

export class TaskCompletionError extends Error {
  constructor(
    message: string,
    public readonly status: TaskStatus,
    public readonly taskKey: string,
  ) {
    super(message);
    this.name = "TaskCompletionError";
  }
}

function resolveTaskProjectId(projectId?: string): string {
  const resolved = (projectId ?? readUrl().project ?? "").trim();
  if (!resolved) {
    throw new Error("project_id is required for task monitoring");
  }
  return resolved;
}

export async function listTasks(projectId?: string): Promise<TaskState[]> {
  const resolved = resolveTaskProjectId(projectId);
  return await apiCall<TaskState[]>(
    `projects/${encodeURIComponent(resolved)}/tasks`,
  );
}

export async function getProjectTaskLimits(projectId: string): Promise<ProjectTaskLimits> {
  const resolved = resolveTaskProjectId(projectId);
  return await apiCall<ProjectTaskLimits>(
    `projects/${encodeURIComponent(resolved)}/tasks/limits`,
  );
}

export async function getTaskByKey(
  task_type: string,
  projectId: string,
  episode: number = 0,
): Promise<TaskState | null> {
  // SuperTale's per-task GET is keyed by (task_type, project_id, episode);
  // for freezone we keep episode=0 and scope-search via the SSE stream
  // for the specific job_id.
  try {
    return await apiCall<TaskState | null>(
      `projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(task_type)}/${episode}`,
    );
  } catch {
    return null;
  }
}

export interface SseHandle {
  close(): void;
}

export interface TaskStreamHandler {
  onTask: (task: TaskState) => void;
  onError?: (err: Event) => void;
  onAuthRevoked?: () => void;
  projectId?: string;
}

/**
 * Open a project SSE stream that fans every `task_updated` event out to the
 * registered handler. Reconnects with exponential backoff on transient errors.
 */
export function openTaskStream(handler: TaskStreamHandler): SseHandle {
  const projectId = resolveTaskProjectId(handler.projectId);
  let es: EventSource | null = null;
  let closed = false;
  let attempt = 0;
  let reconnectTimer: number | null = null;

  const close = () => {
    closed = true;
    if (reconnectTimer != null) window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
    es?.close();
    es = null;
  };
  const handleSessionExpired = () => {
    window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    close();
    handler.onAuthRevoked?.();
  };
  window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);

  const connect = () => {
    if (closed) return;
    es = new EventSource(
      `/api/v1/projects/${encodeURIComponent(projectId)}/tasks/stream?snapshot=false`,
      { withCredentials: true },
    );

    es.addEventListener("task_updated", (event) => {
      attempt = 0;
      try {
        const data = JSON.parse((event as MessageEvent).data);
        handler.onTask(data as TaskState);
      } catch (err) {
        console.warn("[freezone] task_updated parse failed", err);
      }
    });
    es.addEventListener("auth_revoked", () => {
      handler.onAuthRevoked?.();
    });
    es.onerror = (err) => {
      handler.onError?.(err);
      es?.close();
      es = null;
      if (closed) return;
      attempt += 1;
      const delay = Math.min(30_000, 1_000 * 2 ** Math.max(0, attempt - 1));
      reconnectTimer = window.setTimeout(connect, delay);
    };
  };

  connect();

  return {
    close() {
      close();
      window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    },
  };
}

// ---------------------------------------------------------------------- //
// In-process job tracker: callers can `await` a freezone job by task_key
// and the underlying SSE stream resolves the promise on completion / failure.

interface PendingResolver {
  resolve: (task: TaskState) => void;
  reject: (err: Error) => void;
  projectId: string;
  expiresAt: number;
}

type TaskStateEvent = Omit<TaskState, "result"> & {
  result?: unknown | null;
};

interface ProjectPoller {
  timer: number | null;
  inFlight: boolean;
}

const DEFAULT_POLL_INTERVAL_MS = 4000;
const DEFAULT_MAX_POLL_MS = 20 * 60 * 1000;
const pendingByTaskKey = new Map<string, PendingResolver>();
const pollersByProject = new Map<string, ProjectPoller>();

function closeAllTaskMonitoring(err?: Error): void {
  for (const [, poller] of pollersByProject) {
    if (poller.timer != null) {
      window.clearTimeout(poller.timer);
    }
  }
  pollersByProject.clear();

  if (err) {
    for (const [, pending] of pendingByTaskKey) {
      pending.reject(err);
    }
    pendingByTaskKey.clear();
  }
}

function pendingCountForProject(projectId: string): number {
  let count = 0;
  for (const pending of pendingByTaskKey.values()) {
    if (pending.projectId === projectId) count += 1;
  }
  return count;
}

function maybeStopProjectMonitoring(projectId: string): void {
  if (pendingCountForProject(projectId) > 0) return;

  const poller = pollersByProject.get(projectId);
  if (poller) {
    if (poller.timer != null) {
      window.clearTimeout(poller.timer);
    }
    pollersByProject.delete(projectId);
  }

}

function settleTask(task: TaskStateEvent): void {
  const pending = pendingByTaskKey.get(task.task_key);
  if (!pending) return;
  if (task.status === "completed") {
    pending.resolve(task as TaskState);
    pendingByTaskKey.delete(task.task_key);
    maybeStopProjectMonitoring(pending.projectId);
  } else if (task.status === "failed" || task.status === "cancelled") {
    pending.reject(new TaskCompletionError(task.error ?? `task ${task.status}`, task.status, task.task_key));
    pendingByTaskKey.delete(task.task_key);
    maybeStopProjectMonitoring(pending.projectId);
  }
}

/**
 * Feed the app-wide task-center state into node-level task waiters.
 *
 * TaskCenterProvider owns the only long-lived project SSE connection. Canvas
 * generation code consumes that same stream through this function and keeps
 * HTTP polling only as a reconnect/missed-event fallback.
 */
export function publishTaskState(task: TaskStateEvent): void {
  settleTask(task);
}

export function publishTaskSnapshot(tasks: TaskStateEvent[]): void {
  for (const task of tasks) settleTask(task);
}

/**
 * Shared HTTP polling fallback for {@link awaitTaskCompletion}. TaskCenter's
 * project SSE is the primary channel, but it can drop events during reconnect
 * windows. Keep one poller per project so concurrent jobs share one request.
 */
function ensureProjectPoller(projectId: string): void {
  if (pollersByProject.has(projectId)) return;

  const poller: ProjectPoller = { timer: null, inFlight: false };
  pollersByProject.set(projectId, poller);

  const schedule = () => {
    if (!pollersByProject.has(projectId)) return;
    poller.timer = window.setTimeout(run, DEFAULT_POLL_INTERVAL_MS);
  };

  const run = async () => {
    poller.timer = null;
    if (pendingCountForProject(projectId) === 0) {
      pollersByProject.delete(projectId);
      return;
    }
    if (poller.inFlight) {
      schedule();
      return;
    }

    poller.inFlight = true;
    try {
      const tasks = await listTasks(projectId);
      const tasksByKey = new Map(tasks.map((task) => [task.task_key, task]));
      publishTaskSnapshot(tasks);
      const now = Date.now();
      for (const [taskKey, pending] of pendingByTaskKey) {
        if (pending.projectId !== projectId) continue;
        const found = tasksByKey.get(taskKey);
        if (found) {
          settleTask(found);
        }
        // settleTask only settles terminal statuses. If the entry is still
        // pending past its deadline — whether the task went missing OR stays
        // visible but never terminal — time it out so the promise can't hang.
        if (pendingByTaskKey.has(taskKey) && now > pending.expiresAt) {
          pending.reject(new Error("task polling timed out"));
          pendingByTaskKey.delete(taskKey);
        }
      }
    } catch {
      // transient list failure — try again next tick
    } finally {
      poller.inFlight = false;
    }

    if (pendingCountForProject(projectId) === 0) {
      pollersByProject.delete(projectId);
      return;
    }
    schedule();
  };

  schedule();
}

export function awaitTaskCompletion(taskKey: string, projectId: string): Promise<TaskState> {
  const resolved = resolveTaskProjectId(projectId);
  ensureProjectPoller(resolved);
  const promise = new Promise<TaskState>((resolve, reject) => {
    pendingByTaskKey.set(taskKey, {
      resolve,
      reject,
      projectId: resolved,
      expiresAt: Date.now() + DEFAULT_MAX_POLL_MS,
    });
  });
  return promise.finally(() => {
    pendingByTaskKey.delete(taskKey);
    maybeStopProjectMonitoring(resolved);
  });
}

if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    closeAllTaskMonitoring(new Error("task monitor reloaded"));
  });
}
