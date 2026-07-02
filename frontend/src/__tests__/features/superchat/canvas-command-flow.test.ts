import { describe, expect, it } from "vitest";

import {
  buildCanvasCommandFlowItemsForTest,
  canvasCommandFeedbackIsValidationOnlyForTest,
  mergeCanvasContextActivitiesForTest,
  mergeCanvasCommandFeedbacksForTest,
  mergePendingCanvasCommandApprovalForTest,
} from "@/features/superchat/superchat-panel";

describe("canvas command flow placement", () => {
  it("keeps an event after the final assistant text when its saved anchor is missing", () => {
    const items = buildCanvasCommandFlowItemsForTest(
      "前置说明\n最终回复",
      [],
      [
        {
          key: "bridge:layout",
          applied: 1,
          openedUiActions: 0,
          errors: [],
          commandResults: [
            {
              commandIndex: 0,
              type: "layout_nodes",
              status: "success",
              label: "整理布局",
            },
          ],
          anchorTextPrefix: "前置说明\n过程里还没进入最终回复",
          surfaceOrder: 10,
        },
      ],
      [],
    );

    expect(items.map((item) => item.kind)).toEqual(["text", "feedback"]);
    expect(items[0]).toMatchObject({ kind: "text", text: "前置说明\n最终回复" });
  });

  it("prefers persisted feedback anchors over duplicate in-memory feedback anchors", () => {
    const persisted = {
      key: "bridge:layout",
      applied: 1,
      openedUiActions: 0,
      errors: [],
      commandResults: [
        {
          commandIndex: 0,
          type: "layout_nodes",
          status: "success",
          label: "整理布局",
        },
      ],
      anchorTextPrefix: "正文前半段\n",
      surfaceOrder: 20,
    };
    const inMemory = {
      ...persisted,
      anchorTextPrefix: "过程中的临时文本",
      surfaceOrder: 10,
    };

    const items = buildCanvasCommandFlowItemsForTest(
      "正文前半段\n正文后半段",
      [],
      mergeCanvasCommandFeedbacksForTest([persisted], [inMemory]),
      [],
    );

    expect(items.map((item) => item.kind)).toEqual(["text", "feedback", "text"]);
    expect(items[0]).toMatchObject({ kind: "text", text: "正文前半段\n" });
  });

  it("does not treat a cancelled canvas command as validation-only feedback", () => {
    expect(canvasCommandFeedbackIsValidationOnlyForTest({
      key: "bridge:cancelled",
      applied: 0,
      openedUiActions: 0,
      errors: ["已取消画布操作"],
      commandResults: [
        {
          commandIndex: -1,
          type: "validate",
          status: "error",
          label: "已取消",
          error: "已取消画布操作",
        },
      ],
    })).toBe(false);
  });

  it("dedupes the same pending approval when one event resolves the turn later", () => {
    const envelopes = [
      {
        schema_version: "canvas_chat_commands.v1",
        commands: [
          {
            type: "create_node",
            client_id: "kf4",
            node_type: "imageGenNode",
            data: { prompt: "frame" },
          },
        ],
      },
    ];
    const first = {
      id: "canvas-command-approval:tool-canvas-command:1:bridge:bridge-a",
      key: "bridge:bridge-a",
      messageId: "tool-canvas-command:1",
      turnId: null,
      bridgeKey: "bridge-a",
      anchorTextPrefix: null,
      surfaceOrder: 1,
      envelopes,
      commandCount: 1,
      plans: [],
    };
    const second = {
      ...first,
      id: "canvas-command-approval:assistant-turn-a:bridge:bridge-a:turn:turn-a",
      key: "bridge:bridge-a:turn:turn-a",
      messageId: "assistant-turn-a",
      turnId: "turn-a",
      surfaceOrder: 2,
    };

    const merged = mergePendingCanvasCommandApprovalForTest(
      mergePendingCanvasCommandApprovalForTest([], first as any),
      second as any,
    );

    expect(merged).toHaveLength(1);
    expect(merged[0]).toMatchObject({
      id: first.id,
      key: second.key,
      messageId: second.messageId,
      turnId: "turn-a",
    });
  });

  it("merges persisted and live canvas context activities without losing the live anchor", () => {
    const merged = mergeCanvasContextActivitiesForTest(
      [
        {
          key: "context:node-detail",
          turnId: "turn-a",
          bridgeKey: "node-detail",
          status: "done",
          labels: ["节点参数"],
          errors: [],
          anchorTextPrefix: null,
          surfaceOrder: 30,
        },
      ],
      [
        {
          key: "context:node-detail",
          turnId: "turn-a",
          bridgeKey: "node-detail",
          status: "done",
          labels: ["节点参数"],
          errors: [],
          anchorTextPrefix: "验证通过，现在创建节点和连接：\n",
          surfaceOrder: 10,
        },
      ],
    );

    expect(merged).toHaveLength(1);
    expect(merged[0]).toMatchObject({
      anchorTextPrefix: "验证通过，现在创建节点和连接：\n",
      surfaceOrder: 10,
    });
  });

  it("places validation and execution cards before assistant text that describes their result", () => {
    const text = [
      "好的！我来帮你创建一个家乡文化海报的工作流。",
      "",
      "验证通过，创建节点并连接：",
      "",
      "已经在画布上创建好了海报工作流。",
    ].join("\n");

    const items = buildCanvasCommandFlowItemsForTest(
      text,
      [],
      [
        {
          key: "bridge:command",
          applied: 4,
          openedUiActions: 0,
          errors: [],
          commandResults: [
            {
              commandIndex: 0,
              type: "create_node",
              status: "success",
              label: "创建节点",
            },
          ],
          anchorTextPrefix: text,
          surfaceOrder: 40,
        },
      ],
      [
        {
          key: "context:validation",
          turnId: "turn-a",
          bridgeKey: "validation",
          status: "done",
          labels: ["命令校验"],
          errors: [],
          anchorTextPrefix: text,
          surfaceOrder: 30,
        },
      ],
    );

    expect(items.map((item) => item.kind)).toEqual([
      "text",
      "context",
      "text",
      "feedback",
      "text",
    ]);
    expect(items[0]).toMatchObject({
      kind: "text",
      text: "好的！我来帮你创建一个家乡文化海报的工作流。\n\n",
    });
    expect(items[2]).toMatchObject({
      kind: "text",
      text: "验证通过，创建节点并连接：\n\n",
    });
  });

  it("keeps read-context cards next to the assistant text that requested them", () => {
    const text = [
      "我将帮你润色当前视频节点的提示词。首先，我需要获取该节点的详细信息，以便了解其完整内容和可编辑字段。",
      "",
      "现在我已经获取了视频节点的详细信息。当前的提示词是“猫吃鱼”。",
      "",
      "让我为这个提示词提供几个润色选项，从基础增强到专业级：",
    ].join("\n");

    const items = buildCanvasCommandFlowItemsForTest(
      text,
      [],
      [],
      [
        {
          key: "context:node-detail",
          turnId: "turn-a",
          bridgeKey: "node-detail",
          status: "done",
          labels: ["节点详情"],
          errors: [],
          anchorTextPrefix: null,
          surfaceOrder: 10,
        },
      ],
    );

    expect(items.map((item) => item.kind)).toEqual(["text", "context", "text"]);
    expect(items[0]).toMatchObject({
      kind: "text",
      text: "我将帮你润色当前视频节点的提示词。首先，我需要获取该节点的详细信息，以便了解其完整内容和可编辑字段。\n\n",
    });
    expect(items[2]).toMatchObject({
      kind: "text",
      text: "现在我已经获取了视频节点的详细信息。当前的提示词是“猫吃鱼”。\n\n让我为这个提示词提供几个润色选项，从基础增强到专业级：",
    });
  });
});
