// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import type { TaskLogEntry } from "@/task-center/types";

export type TaskStatus =
  | "submitting"
  | "queued"
  | "pending"
  | "starting"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface Task {
  task_id?: string;
  task_type: string;
  username: string;
  project: string;
  project_id?: string;
  episode: number;
  beat_num?: number;
  scope?: string;
  status: TaskStatus;
  progress: number;
  current_task?: string;
  current_task_code?: string | null;
  current_task_params?: Record<string, unknown> | null;
  result?: unknown;
  metadata?: Record<string, unknown>;
  error?: string;
  logs?: TaskLogEntry[];
  created_at?: string;
  task_type_label?: string;
  display_name?: string;
}

export interface TaskStreamEvent {
  status: TaskStatus;
  progress: number;
  current_task?: string;
  /** current_task 的 i18n 词条 key；后端还没迁移的调用点没有这个字段。 */
  current_task_code?: string | null;
  current_task_params?: Record<string, unknown> | null;
  result?: unknown;
  error?: string;
  error_code?: string | null;
  logs?: TaskLogEntry[];
}

// Re-export the task-center canonical types so new code can import from either
// `@/types/task` or `@/task-center/types` and get the same truth.
export type { TaskLogEntry, TaskState } from "@/task-center/types";
