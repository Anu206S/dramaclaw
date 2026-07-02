// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
export type ClientFrame =
  | {
      type: "chat.message";
      scope?: ChatScope;
      text: string;
      turn_id?: string;
      attachments?: ChatAttachment[];
      surface?: "freezone";
      context?: {
        freezone_canvas_id?: string | null;
      };
    }
  | {
      type: "scope.set";
      scope: ChatScope;
      history_limit?: number;
      history_before?: string | null;
    }
  | {
      type: "canvas.context.result";
      turn_id?: string | null;
      bridge_key: string;
      project_id?: string | null;
      canvas_id?: string | null;
      tool_call_status?: "completed" | "cancelled" | "failed";
      ok: boolean;
      responses?: Array<Record<string, unknown>>;
      errors?: string[];
      message?: string | null;
    }
  | {
      type: "canvas.command.result";
      turn_id?: string | null;
      bridge_key: string;
      project_id?: string | null;
      canvas_id?: string | null;
      tool_call_status?: "completed" | "cancelled" | "failed";
      canvas_apply_status: "applied" | "partially_applied" | "failed" | "cancelled_by_user";
      applied?: boolean;
      cancelled?: boolean;
      errors?: string[];
      applied_count?: number;
      opened_ui_actions?: number;
      created_node_ids?: string[];
      command_results?: Array<Record<string, unknown>>;
      message?: string | null;
    };

export type ChatScope = {
  kind: "home" | "project" | "freezone" | "asset" | "task";
  id?: string | null;
  surface?: "director" | "freezone" | null;
  canvasId?: string | null;
};

export type RelayInstanceInfo = {
  instanceId: string;
  instanceName: string;
  ip?: string;
  connectedAt?: number;
  busy?: boolean;
};

export type ModelEntry = {
  id: string;
  label: string;
  reasoning?: boolean;
};

export type SessionControlCommand =
  | "agents"
  | "compact"
  | "fast"
  | "kill"
  | "model"
  | "redirect"
  | "steer"
  | "think"
  | "usage"
  | "verbose";

export type ServerFrame =
  | {
      type: "scope.changed";
      scope: ChatScope;
      history: unknown[];
      busy?: boolean;
    }
  | {
      type: "chat.busy";
      scope?: ChatScope;
      turn_id?: string;
      message?: string;
    }
  | {
      type: "chat.ping";
      scope?: ChatScope;
      turn_id?: string;
    }
  | {
      type: "thread.started";
      scope?: ChatScope;
      thread_id?: string | null;
      turn_id?: string;
    }
  | {
      type: "assistant.delta";
      text?: string;
      turn_id?: string;
      accumulated?: boolean;
    }
  | {
      type: "assistant.message";
      message?: unknown;
      turn_id?: string;
    }
  | {
      type: "tool.result";
      turn_id?: string;
      name?: string;
      success?: boolean;
      result?: unknown;
      error?: unknown;
      bridge_key?: string;
    }
  | {
      type: "tool.call";
      turn_id?: string;
      name?: string;
      input?: unknown;
      raw?: unknown;
      bridge_key?: string;
    }
  | {
      type: "history.page";
      scope?: ChatScope;
      history: unknown[];
      before?: string | null;
      has_more?: boolean;
    }
  | {
      type: "canvas.command";
      turn_id?: string;
      bridge_key?: string;
      project_id?: string | null;
      canvas_id?: string | null;
      envelope?: unknown;
      envelopes?: unknown[];
      command?: unknown;
      commands?: unknown[];
      anchor_text_prefix?: string | null;
      received_at?: number;
    }
  | {
      type: "canvas.context.request";
      turn_id?: string;
      bridge_key?: string;
      project_id?: string | null;
      canvas_id?: string | null;
      envelope?: unknown;
      envelopes?: unknown[];
      request?: unknown;
      requests?: unknown[];
      anchor_text_prefix?: string | null;
      received_at?: number;
    }
  | {
      type: "stop_reason";
      reason?: string;
      turn_id?: string;
    }
  | { type: "chat.done"; turn_id?: string; scope?: ChatScope }
  | { type: "project.created"; project: string }
  | { type: "error"; message: string; turn_id?: string }
  | { type: string; [key: string]: unknown };

export type ChatRole = "user" | "assistant" | "system" | "tool";

export type ChatAttachment = {
  id?: string;
  type?: string;
  kind?: string;
  mimeType?: string;
  fileName?: string;
  fileSize?: number;
  content?: string;
  url?: string;
  path?: string;
  label?: string;
};

export type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
  turnId?: string;
  displayName?: string;
  attachments?: ChatAttachment[];
  uiEvents?: unknown[];
  timestamp: number;
  raw?: unknown;
};

export type ApprovalRequest = {
  id: string;
  kind: "exec" | "plugin";
  title: string;
  command?: string;
  description?: string;
  cwd?: string | null;
  host?: string | null;
  security?: string | null;
  agentId?: string | null;
  sessionKey?: string | null;
  expiresAtMs?: number;
};

export type SuperChatSettings = {
  showToolEvents: boolean;
  showStructuredSourceWhileStreaming: boolean;
  uploadTarget: "openclaw" | "local";
};
