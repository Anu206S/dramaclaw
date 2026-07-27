// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { describe, expect, it } from "vitest";

import { selectChatTaskItems } from "@/features/superchat/chat-task-status-bar";
import type { CanvasNode } from "@/features/canvas/domain/canvasNodes";
import type { TaskState } from "@/task-center/types";

const NOW = Date.parse("2026-07-27T08:00:00.000Z");

function task(overrides: Partial<TaskState> = {}): TaskState {
  return {
    task_key: "task-1",
    task_id: "job-1",
    task_type: "freezone_image",
    username: "local",
    project: "project-1",
    project_id: "project-1",
    episode: 0,
    beat_num: null,
    scope: null,
    status: "running",
    progress: 0.5,
    current_task: "Generating",
    result: null,
    metadata: null,
    error: null,
    logs: [],
    created_at: "2026-07-27T07:59:00.000Z",
    updated_at: "2026-07-27T07:59:30.000Z",
    completed_at: "",
    ...overrides,
  };
}

function node(overrides: Partial<CanvasNode> = {}): CanvasNode {
  return {
    id: "node-1",
    type: "imageGen",
    position: { x: 0, y: 0 },
    data: {
      displayName: "商品主图",
      generationTaskKey: "task-1",
    },
    ...overrides,
  } as CanvasNode;
}

describe("selectChatTaskItems", () => {
  it("matches a task through the canvas node generation key", () => {
    const result = selectChatTaskItems([task()], [node()], "canvas-1", NOW);

    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      nodeId: "node-1",
      nodeLabel: "商品主图",
    });
  });

  it("matches task metadata for the current canvas and excludes another canvas", () => {
    const current = task({
      task_key: "current",
      metadata: { canvas_id: "canvas-1" },
    });
    const other = task({
      task_key: "other",
      metadata: { canvas_id: "canvas-2" },
    });

    const result = selectChatTaskItems([current, other], [], "canvas-1", NOW);

    expect(result.map(({ task: item }) => item.task_key)).toEqual(["current"]);
  });

  it("keeps recent terminal tasks and hides expired terminal tasks", () => {
    const recent = task({
      task_key: "recent",
      status: "completed",
      completed_at: "2026-07-27T07:59:30.000Z",
      metadata: { canvas_id: "canvas-1" },
    });
    const expired = task({
      task_key: "expired",
      status: "failed",
      completed_at: "2026-07-27T07:58:00.000Z",
      metadata: { canvas_id: "canvas-1" },
    });

    const result = selectChatTaskItems([recent, expired], [], "canvas-1", NOW);

    expect(result.map(({ task: item }) => item.task_key)).toEqual(["recent"]);
  });

  it("puts active tasks before recent terminal tasks", () => {
    const completed = task({
      task_key: "completed",
      status: "completed",
      completed_at: "2026-07-27T07:59:50.000Z",
      metadata: { canvas_id: "canvas-1" },
    });
    const running = task({
      task_key: "running",
      updated_at: "2026-07-27T07:59:20.000Z",
      metadata: { canvas_id: "canvas-1" },
    });

    const result = selectChatTaskItems([completed, running], [], "canvas-1", NOW);

    expect(result.map(({ task: item }) => item.task_key)).toEqual([
      "running",
      "completed",
    ]);
  });
});
