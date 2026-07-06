// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { beforeEach, describe, expect, it, vi } from "vitest";

import { reportCanvasCommandToolResult } from "@/features/freezone/canvasCommandToolResult";
import { reportCanvasContextToolResult } from "@/features/freezone/canvasContextToolResult";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: {
    post: vi.fn(() => Promise.resolve({ ok: true })),
  },
}));

describe("Freezone canvas tool result reporting", () => {
  beforeEach(() => {
    vi.mocked(api.post).mockClear();
  });

  it("reports canvas command results with the originating agent id", () => {
    reportCanvasCommandToolResult({
      bridgeKey: "bridge-a",
      turnId: "turn-a",
      projectId: "project-a",
      canvasId: "canvas-a",
      agentId: "agent-2",
      result: {
        applied: 1,
        openedUiActions: 0,
        createdNodeIds: ["node-a"],
        errors: [],
        commandResults: [
          {
            commandIndex: 0,
            type: "create_node",
            status: "success",
            label: "创建节点",
          },
        ],
      },
    });

    expect(api.post).toHaveBeenCalledWith("api/v1/chat/canvas-command-tool-result", {
      json: expect.objectContaining({ agent_id: "agent-2" }),
      timeout: 30_000,
    });
  });

  it("reports canvas context results with the originating agent id", () => {
    reportCanvasContextToolResult({
      bridgeKey: "bridge-a",
      turnId: "turn-a",
      projectId: "project-a",
      canvasId: "canvas-a",
      agentId: "agent-2",
      responses: [{ ok: true }],
    });

    expect(api.post).toHaveBeenCalledWith("api/v1/chat/canvas-context-tool-result", {
      json: expect.objectContaining({ agent_id: "agent-2" }),
      timeout: 30_000,
    });
  });
});
