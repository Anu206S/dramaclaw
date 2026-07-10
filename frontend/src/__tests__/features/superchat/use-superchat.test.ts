// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { normalizeMessage } from "@/features/superchat/message";
import { buildCanvasCommandToolResultPayloadForTest } from "@/features/freezone/canvasCommandToolResult";
import {
  SUPERCHAT_CANVAS_COMMAND_EVENT,
  canvasContextToolResultFrameForTest,
  dispatchCanvasCommandFrameForTest,
  mergeHistorySnapshot,
  normalizeMessageForScopeForTest,
  pruneOldMessageCaches,
  resolveUiEventTurnIdForTest,
  sanitizeMessagesForCache,
  scopeForProjectForTest,
  scopeSessionKeyForTest,
  updateAssistantUiEventsForTest,
  upsertAssistantUiEventForTest,
  upsertServerAssistantMessageForTest,
  useSuperChat,
} from "@/features/superchat/use-superchat";
import {
  CANVAS_NODE_REFERENCE_ATTACHMENT_TYPE,
  CANVAS_NODE_REFERENCE_SCHEMA_VERSION,
  isCanvasNodeReferenceAttachment,
} from "@/features/freezone/chatNodeReferences";
import {
  buildAssistantClarificationResponseForTest,
  buildAssistantClarificationToolResultForTest,
  buildSkillStudioCatalogSaveItemsForTest,
  buildSkillStudioDraftCancelToolResultForTest,
  buildSkillStudioDraftToolResultForTest,
  skillStudioDraftFieldLabelsForTest,
  buildSkillStudioFlowItemsForTest,
  buildSkillStudioQuestionTimelineItemsForTest,
  buildSkillStudioQuestionResponseForTest,
  buildSkillStudioQuestionToolResultForTest,
  messageIsWaitingForUserReplyForTest,
  messageHasSkillStudioUiEventForTest,
  shouldHideSkillStudioStatusOnlyMessageForTest,
  shouldShowComposerWaitingIndicator,
  skillStudioEventsFromUiEventsForTest,
  visibleCanvasContextActivitiesForMessageForTest,
  visibleSkillStudioEventsForMessageForTest,
} from "@/features/superchat/superchat-panel";
import type { ChatMessage, ChatRole } from "@/features/superchat/types";

const MESSAGE_CACHE_PREFIX = "superchat:messages:v2:";
const DAY_MS = 24 * 60 * 60 * 1000;

function message(
  id: string,
  role: ChatRole,
  text: string,
  timestamp: number,
  turnId?: string,
): ChatMessage {
  return { id, role, text, timestamp, turnId };
}

describe("mergeHistorySnapshot", () => {
  it("replaces local turn messages with matching backend history", () => {
    const current = [
      message("user-turn-1", "user", "你好", 10, "turn-1"),
      message("assistant-turn-1", "assistant", "你好，有什么可以帮你？", 20, "turn-1"),
    ];
    const history = [
      message("backend-user-1", "user", "你好", 30),
      message("backend-assistant-1", "assistant", "你好，有什么可以帮你？", 40),
    ];

    const merged = mergeHistorySnapshot(current, history, "turn-1");

    expect(merged.map((item) => item.id)).toEqual(["backend-user-1", "backend-assistant-1"]);
  });

  it("replaces a completed local turn when the final local delta is newer than backend history", () => {
    const current = [
      message("user-turn-1", "user", "你好", 100, "turn-1"),
      message("assistant-turn-1", "assistant", "你好，有什么可以帮你？", 300, "turn-1"),
    ];
    const history = [
      message("backend-user-1", "user", "你好", 150),
      message("backend-assistant-1", "assistant", "你好，有什么可以帮你？", 250),
    ];

    const merged = mergeHistorySnapshot(current, history, "turn-1");

    expect(merged.map((item) => item.id)).toEqual(["backend-user-1", "backend-assistant-1"]);
  });

  it("replaces a completed local turn even when local partial text differs", () => {
    const current = [
      message("user-turn-1", "user", "你好", 100, "turn-1"),
      message("assistant-turn-1", "assistant", "正在生成", 120, "turn-1"),
    ];
    const history = [
      message("backend-user-1", "user", "你好", 150),
      message("backend-assistant-1", "assistant", "你好！有什么我可以帮你的吗？", 250),
    ];

    const merged = mergeHistorySnapshot(current, history, "turn-1");

    expect(merged.map((item) => item.id)).toEqual(["backend-user-1", "backend-assistant-1"]);
  });

  it("keeps the protected in-flight turn when a stale snapshot has the same user text", () => {
    const current = [
      message("backend-user-1", "user", "你好", 10),
      message("backend-assistant-1", "assistant", "第一轮回复", 20),
      message("user-turn-2", "user", "你好", 30, "turn-2"),
      message("assistant-turn-2", "assistant", "正在生成", 40, "turn-2"),
    ];
    const staleHistory = [
      message("backend-user-1", "user", "你好", 10),
      message("backend-assistant-1", "assistant", "第一轮回复", 20),
    ];

    const merged = mergeHistorySnapshot(current, staleHistory, "turn-2");

    expect(merged.map((item) => item.id)).toEqual([
      "backend-user-1",
      "backend-assistant-1",
      "user-turn-2",
      "assistant-turn-2",
    ]);
  });

  it("keeps a protected assistant reply even when it resembles an earlier turn", () => {
    const current = [
      message("backend-user-1", "user", "你好", 10, "turn-1"),
      message("backend-assistant-1", "assistant", "你好，有什么可以帮你？", 20, "turn-1"),
      message("user-turn-2", "user", "你好", 30, "turn-2"),
      message("assistant-turn-2", "assistant", "你好，有什么可以帮你？", 40, "turn-2"),
    ];
    const staleHistory = [
      message("backend-user-1", "user", "你好", 10, "turn-1"),
      message("backend-assistant-1", "assistant", "你好，有什么可以帮你？", 20, "turn-1"),
    ];

    const merged = mergeHistorySnapshot(current, staleHistory, "turn-2");

    expect(merged.map((item) => item.id)).toEqual([
      "backend-user-1",
      "backend-assistant-1",
      "user-turn-2",
      "assistant-turn-2",
    ]);
  });

  it("does not collapse repeated completed turns from backend history", () => {
    const history = [
      message("backend-user-1", "user", "你好", 10),
      message("backend-assistant-1", "assistant", "回复", 20),
      message("backend-user-2", "user", "你好", 30),
      message("backend-assistant-2", "assistant", "回复", 40),
    ];

    const merged = mergeHistorySnapshot([], history);

    expect(merged.map((item) => item.id)).toEqual([
      "backend-user-1",
      "backend-assistant-1",
      "backend-user-2",
      "backend-assistant-2",
    ]);
  });

  it("drops unprotected local assistant leftovers when backend history arrives", () => {
    const current = [
      message("backend-user-1", "user", "第一句", 10),
      message("backend-assistant-1", "assistant", "第一轮回复", 20),
      message("assistant-stale", "assistant", "上次残留的回复", 30, "turn-stale"),
    ];
    const history = [
      message("backend-user-1", "user", "第一句", 10),
      message("backend-assistant-1", "assistant", "第一轮回复", 20),
    ];

    const merged = mergeHistorySnapshot(current, history);

    expect(merged.map((item) => item.id)).toEqual(["backend-user-1", "backend-assistant-1"]);
  });

  it("keeps locally submitted prompt state when history still has the pending card", () => {
    const current: ChatMessage[] = [
      message("backend-user-1", "user", "我想创建一个宣传海报 skill", 10, "turn-1"),
      {
        id: "assistant-turn-1",
        role: "assistant",
        text: "",
        timestamp: 30,
        turnId: "turn-1",
        uiEvents: [
          {
            type: "skill_studio.questions",
            bridge_key: "skill-key-1",
            skill_studio_session_id: "studio-1",
            questions: [],
            submitted: true,
            action: "submit",
            selections: { audience: { option_ids: ["locals"], custom_text: "" } },
          },
        ],
      },
    ];
    const history: ChatMessage[] = [
      message("backend-user-1", "user", "我想创建一个宣传海报 skill", 10, "turn-1"),
      {
        id: "backend-assistant-1",
        role: "assistant",
        text: "",
        timestamp: 20,
        turnId: "turn-1",
        uiEvents: [
          {
            type: "skill_studio.questions",
            bridge_key: "skill-key-1",
            skill_studio_session_id: "studio-1",
            questions: [],
          },
        ],
      },
    ];

    const merged = mergeHistorySnapshot(current, history, "turn-1");
    const assistant = merged.find((item) => item.role === "assistant");

    expect(assistant?.uiEvents?.[0]).toMatchObject({
      type: "skill_studio.questions",
      bridge_key: "skill-key-1",
      submitted: true,
      action: "submit",
      selections: { audience: { option_ids: ["locals"], custom_text: "" } },
    });
  });

  it("keeps locally edited draft state when history still has the original draft", () => {
    const current: ChatMessage[] = [
      message("backend-user-1", "user", "生成 skill 草稿", 10, "turn-1"),
      {
        id: "assistant-turn-1",
        role: "assistant",
        text: "",
        timestamp: 30,
        turnId: "turn-1",
        uiEvents: [
          {
            type: "skill_studio.draft",
            bridge_key: "draft-key-1",
            skill_studio_session_id: "studio-1",
            draft: {
              skill: { id: "edited-skill", description: "编辑后的草稿" },
              recipes: [],
            },
          },
        ],
      },
    ];
    const history: ChatMessage[] = [
      message("backend-user-1", "user", "生成 skill 草稿", 10, "turn-1"),
      {
        id: "backend-assistant-1",
        role: "assistant",
        text: "",
        timestamp: 20,
        turnId: "turn-1",
        uiEvents: [
          {
            type: "skill_studio.draft",
            bridge_key: "draft-key-1",
            skill_studio_session_id: "studio-1",
            skill: { id: "original-skill", description: "原始草稿" },
            recipes: [],
          },
        ],
      },
    ];

    const merged = mergeHistorySnapshot(current, history, "turn-1");
    const assistant = merged.find((item) => item.role === "assistant");

    expect(assistant?.uiEvents).toHaveLength(1);
    expect(assistant?.uiEvents?.[0]).toMatchObject({
      type: "skill_studio.draft",
      bridge_key: "draft-key-1",
      draft: {
        skill: { id: "edited-skill", description: "编辑后的草稿" },
      },
    });
  });
});

describe("normalizeMessage", () => {
  it("strips internal DramaClaw context blocks from displayed text", () => {
    const normalized = normalizeMessage({
      id: "backend-user-1",
      role: "user",
      content: `上传了哪些文件了

[DRAMACLAW_UPLOADED_FILES]
dramaclaw_project_id: 01KT62KTBQCDR69WW889VHJR3N
file_1_filename: 她与她的江山.docx
[/DRAMACLAW_UPLOADED_FILES]`,
      created_at: "2026-06-03T09:00:00Z",
    });

    expect(normalized?.text).toBe("上传了哪些文件了");
  });

  it("strips internal SuperTale canvas command blocks from displayed text", () => {
    const normalized = normalizeMessage({
      id: "backend-user-2",
      role: "user",
      content: `你好

[SUPERTALE_CANVAS_CHAT_COMMANDS]
This Freezone chat can change the current canvas by returning a JSON block.
[/SUPERTALE_CANVAS_CHAT_COMMANDS]`,
      created_at: "2026-06-08T08:00:00Z",
    });

    expect(normalized?.text).toBe("你好");
  });

  it("maps internal empty Hermes replies to a user-facing message", () => {
    const normalized = normalizeMessage({
      id: "backend-assistant-empty",
      role: "assistant",
      content: "(hermes returned no content)",
      created_at: "2026-07-10T08:00:00Z",
    });

    expect(normalized?.text).toBe("这轮操作没有收到虾导的有效回复，请稍后重试。");
  });

  it("preserves backend ui events for persisted canvas feedback", () => {
    const uiEvents = [
      {
        type: "canvas_command_result",
        bridge_key: "bridge-a",
      },
    ];
    const normalized = normalizeMessage({
      id: "assistant-1",
      role: "assistant",
      content: "已完成",
      ui_events: uiEvents,
    });

    expect(normalized?.uiEvents).toBe(uiEvents);
  });
});

describe("normalizeMessageForScope", () => {
  const freezoneScope = scopeForProjectForTest("project-a", "freezone", "canvas-a", "agent-a");
  const directorScope = scopeForProjectForTest("project-a", "director");
  const canvasReferencePayload = {
    schema_version: CANVAS_NODE_REFERENCE_SCHEMA_VERSION,
    project: "project-a",
    canvas_id: "canvas-a",
    nodes: [
      {
        node_id: "node-text",
        node_type: "textAnnotationNode",
        label: "文本",
        text_field: "content",
        text_content: "你好",
        media_type: null,
        source_url: null,
        preview_url: null,
        slot_target: null,
        mainline_context: null,
        candidate_origin: null,
        position: { x: 0, y: 0 },
        action_catalog: { actions: [] },
      },
    ],
    edges: [],
  };
  const canvasReferenceMedia = {
    id: "canvas_node_reference:文本",
    kind: CANVAS_NODE_REFERENCE_ATTACHMENT_TYPE,
    type: CANVAS_NODE_REFERENCE_ATTACHMENT_TYPE,
    label: "文本",
    content: JSON.stringify(canvasReferencePayload),
  };

  it("hydrates cached Freezone canvas node references from raw media", () => {
    const normalized = normalizeMessageForScopeForTest(
      {
        id: "user-1",
        role: "user",
        text: "帮我连接到图片节点",
        attachments: [
          {
            id: "canvas_node_reference:文本",
            type: CANVAS_NODE_REFERENCE_ATTACHMENT_TYPE,
            kind: CANVAS_NODE_REFERENCE_ATTACHMENT_TYPE,
            label: "文本",
            fileName: "文本",
          },
        ],
        rawMedia: [canvasReferenceMedia],
      },
      "assistant",
      freezoneScope,
    );

    expect(normalized?.attachments).toHaveLength(1);
    expect(normalized?.attachments?.[0].content).toBe(JSON.stringify(canvasReferencePayload));
    expect(isCanvasNodeReferenceAttachment(normalized!.attachments![0])).toBe(true);
  });

  it("does not hydrate canvas node references for the director scope", () => {
    const normalized = normalizeMessageForScopeForTest(
      {
        id: "user-1",
        role: "user",
        text: "帮我连接到图片节点",
        attachments: [
          {
            id: "canvas_node_reference:文本",
            type: CANVAS_NODE_REFERENCE_ATTACHMENT_TYPE,
            kind: CANVAS_NODE_REFERENCE_ATTACHMENT_TYPE,
            label: "文本",
            fileName: "文本",
          },
        ],
        rawMedia: [canvasReferenceMedia],
      },
      "assistant",
      directorScope,
    );

    expect(normalized?.attachments).toEqual([]);
  });
});

describe("upsertServerAssistantMessage", () => {
  it("preserves transient ui events when the final assistant message arrives", () => {
    const uiEvent = {
      type: "skill_studio.questions",
      skill_studio_session_id: "skill_studio_01",
      questions: [],
    };
    const current: ChatMessage[] = [
      message("user-turn-1", "user", "创建 Skill", 10, "turn-1"),
      {
        id: "assistant-turn-1",
        role: "assistant",
        text: "",
        timestamp: 20,
        turnId: "turn-1",
        uiEvents: [uiEvent],
      },
    ];

    const merged = upsertServerAssistantMessageForTest(
      current,
      {
        id: 3,
        role: "assistant",
        content: "已进入问答环节",
        turn_id: "turn-1",
        created_at: "2026-07-08T03:47:06.538231+00:00",
      },
      "turn-1",
    );

    const assistant = merged.find((item) => item.role === "assistant");
    expect(assistant?.text).toBe("已进入问答环节");
    expect(assistant?.uiEvents).toEqual([uiEvent]);
  });

  it("merges same draft ui event when the final assistant message arrives", () => {
    const current: ChatMessage[] = [
      message("user-turn-1", "user", "创建 Skill", 10, "turn-1"),
      {
        id: "assistant-turn-1",
        role: "assistant",
        text: "",
        timestamp: 20,
        turnId: "turn-1",
        uiEvents: [
          {
            type: "skill_studio.draft",
            bridge_key: "draft-key-1",
            skill_studio_session_id: "studio-1",
            skill: { id: "original-skill" },
          },
          {
            type: "skill_studio.draft",
            bridge_key: "draft-key-1",
            skill_studio_session_id: "studio-1",
            draft: { skill: { id: "edited-skill" }, recipes: [] },
          },
        ],
      },
    ];

    const merged = upsertServerAssistantMessageForTest(
      current,
      {
        id: 3,
        role: "assistant",
        content: "继续处理",
        turn_id: "turn-1",
        created_at: "2026-07-08T03:47:06.538231+00:00",
      },
      "turn-1",
    );

    const assistant = merged.find((item) => item.role === "assistant");
    expect(assistant?.uiEvents).toHaveLength(1);
    expect(assistant?.uiEvents?.[0]).toMatchObject({
      type: "skill_studio.draft",
      bridge_key: "draft-key-1",
      draft: { skill: { id: "edited-skill" } },
    });
  });
});

describe("updateAssistantUiEvents", () => {
  it("persists submitted Skill Studio question selections on the assistant message", () => {
    const current: ChatMessage[] = [
      {
        id: "assistant-turn-1",
        role: "assistant",
        text: "",
        timestamp: 20,
        turnId: "turn-1",
        uiEvents: [
          {
            type: "skill_studio.questions",
            skill_studio_session_id: "skill_studio_01",
            questions: [],
          },
        ],
      },
    ];

    const next = updateAssistantUiEventsForTest(
      current,
      "turn-1",
      (event) =>
        Boolean(
          event
            && typeof event === "object"
            && (event as Record<string, unknown>).type === "skill_studio.questions",
        ),
      (event) => ({
        ...(event as Record<string, unknown>),
        submitted: true,
        action: "submit",
        selections: { audience: "young" },
      }),
    );

    expect(next[0]?.uiEvents?.[0]).toMatchObject({
      type: "skill_studio.questions",
      submitted: true,
      action: "submit",
      selections: { audience: "young" },
    });
  });
});

describe("Skill Studio question response", () => {
  it("uses the server turn id for incoming UI events before pending local turns", () => {
    expect(resolveUiEventTurnIdForTest("server-turn", "pending-turn", "active-turn")).toBe("server-turn");
    expect(resolveUiEventTurnIdForTest("  ", "pending-turn", "active-turn")).toBe("pending-turn");
    expect(resolveUiEventTurnIdForTest(null, null, "active-turn")).toBe("active-turn");
  });

  it("hides generic waiting status while a composer prompt is active", () => {
    expect(shouldShowComposerWaitingIndicator({
      busy: true,
      hasAssistantText: false,
      streamText: "",
      pendingCanvasCommandApprovalCount: 0,
      hasPendingVisibleUserMessage: true,
      hasThinkingCanvasContextActivity: false,
      hasActiveComposerPrompt: true,
    })).toBe(false);
  });

  it("keeps an existing assistant event message in its original timeline position", () => {
    const current = [
      message("assistant-turn-1", "assistant", "", 10, "turn-1"),
      message("user-turn-2", "user", "用户提交后的下一条消息", 20, "turn-2"),
    ];

    const next = upsertAssistantUiEventForTest(current, "turn-1", {
      type: "assistant.clarification.request",
      clarification_id: "clarify-1",
      submitted: true,
    });

    expect(next.map((item) => item.id)).toEqual(["assistant-turn-1", "user-turn-2"]);
    expect(next[0]?.timestamp).toBe(10);
    expect(next[0]?.uiEvents?.[0]).toMatchObject({
      type: "assistant.clarification.request",
      clarification_id: "clarify-1",
    });
  });

  it("marks an assistant message with pending questions as waiting for the user", () => {
    const pending = message("assistant-skill-question", "assistant", "", 100);
    pending.uiEvents = [
      {
        type: "skill_studio.questions",
        title: "创建宣传海报 Skill",
        questions: [
          {
            id: "audience",
            title: "目标受众是谁？",
            options: [{ id: "locals", label: "本地居民" }],
          },
        ],
      },
    ];

    const submitted = message("assistant-skill-question-done", "assistant", "", 100);
    submitted.uiEvents = [
      {
        type: "skill_studio.questions",
        submitted: true,
        title: "创建宣传海报 Skill",
        questions: [],
      },
    ];

    expect(messageIsWaitingForUserReplyForTest(pending)).toBe(true);
    expect(messageIsWaitingForUserReplyForTest(submitted)).toBe(false);
  });

  it("builds a chat message from selected card options", () => {
    const text = buildSkillStudioQuestionResponseForTest(
      {
        type: "skill_studio.questions",
        skill_studio_session_id: "skill_studio_01",
        title: "创建宣传海报 Skill",
        questions: [
          {
            id: "audience",
            title: "核心使用场景是什么？",
            options: [
              { id: "social", label: "用于社媒平台发布", description: "小红书/抖音等" },
            ],
          },
          {
            id: "style",
            title: "偏好的视觉风格是？",
            options: [
              { id: "ink", label: "水墨国风/新中式" },
              { id: "modern", label: "现代简约/信息图风" },
            ],
          },
        ],
      },
      { audience: "social", style: "modern" },
    );

    expect(text).toContain("Skill Studio 会话：skill_studio_01");
    expect(text).toContain("创建宣传海报 Skill");
    expect(text).toContain("核心使用场景是什么？：用于社媒平台发布（小红书/抖音等）");
    expect(text).toContain("偏好的视觉风格是？：现代简约/信息图风");
    expect(text).toContain("用户已完成选择，请结合当前上下文继续。");
    expect(text).not.toContain("继续生成 Skill / Recipe 草稿");
  });

  it("keeps unanswered questions visible when partially submitted", () => {
    const text = buildSkillStudioQuestionResponseForTest(
      {
        type: "skill_studio.questions",
        skill_studio_session_id: "skill_studio_01",
        questions: [
          {
            id: "audience",
            title: "核心使用场景是什么？",
            options: [{ id: "social", label: "用于社媒平台发布" }],
          },
          {
            id: "style",
            title: "偏好的视觉风格是？",
            options: [{ id: "modern", label: "现代简约/信息图风" }],
          },
        ],
      },
      { audience: "social" },
    );

    expect(text).toContain("核心使用场景是什么？：用于社媒平台发布");
    expect(text).toContain("偏好的视觉风格是？：未选择");
  });

  it("describes multiple options and custom text in question answers", () => {
    const text = buildSkillStudioQuestionResponseForTest(
      {
        type: "skill_studio.questions",
        skill_studio_session_id: "skill_studio_multi",
        questions: [
          {
            id: "elements",
            title: "海报通常需要包含哪些内容元素？",
            selection_mode: "multiple",
            options: [
              { id: "intro", label: "家乡名称与简介" },
              { id: "feature", label: "特色图片/插画" },
              { id: "slogan", label: "宣传标语" },
            ],
          },
        ],
      },
      {
        elements: {
          option_ids: ["intro", "feature"],
          custom_text: "再加一个适合社媒传播的互动话题",
        },
      },
    );

    expect(text).toContain("海报通常需要包含哪些内容元素？：家乡名称与简介；特色图片/插画；补充：再加一个适合社媒传播的互动话题");
  });

  it("builds compact timeline items for submitted question cards", () => {
    const items = buildSkillStudioQuestionTimelineItemsForTest(
      [
        {
          id: "audience",
          title: "目标受众是谁？",
          options: [{ id: "travelers", label: "外地游客", description: "潜在旅行者" }],
        },
        {
          id: "elements",
          title: "希望突出哪些内容？",
          selection_mode: "multiple",
          options: [
            { id: "food", label: "地方美食" },
            { id: "heritage", label: "非遗文化" },
          ],
        },
        {
          id: "extra",
          title: "其他补充",
          options: [],
        },
      ],
      {
        audience: "travelers",
        elements: {
          option_ids: ["food", "heritage"],
          custom_text: "突出苏州桃花坞年画",
        },
      },
    );

    expect(items).toEqual([
      {
        key: "audience",
        title: "目标受众是谁？",
        summary: "外地游客（潜在旅行者）",
        answered: true,
      },
      {
        key: "elements",
        title: "希望突出哪些内容？",
        summary: "地方美食；非遗文化；补充：突出苏州桃花坞年画",
        answered: true,
      },
      {
        key: "extra",
        title: "其他补充",
        summary: "未选择",
        answered: false,
      },
    ]);
  });

  it("builds a bridge tool result payload instead of a new chat message", () => {
    const payload = buildSkillStudioQuestionToolResultForTest(
      {
        type: "skill_studio.questions",
        bridge_key: "skill-key-1",
        project_id: "project-a",
        canvas_id: "canvas-a",
        agent_id: "agent-1",
        turn_id: "turn-a",
        skill_studio_session_id: "skill_studio_01",
        questions: [
          {
            id: "scope",
            title: "主要做什么？",
            options: [{ id: "planning", label: "策划" }],
          },
        ],
      },
      { scope: "planning" },
    );

    expect(payload).toMatchObject({
      bridge_key: "skill-key-1",
      project_id: "project-a",
      canvas_id: "canvas-a",
      agent_id: "agent-1",
      turn_id: "turn-a",
      tool_call_status: "completed",
      skill_studio_status: "answered",
      action: "submit",
      selections: { scope: "planning" },
      ok: true,
    });
    expect(payload.message).toContain("主要做什么？：策划");
  });

  it("summarizes canvas command failures without exposing protocol details to users", () => {
    const payload = buildCanvasCommandToolResultPayloadForTest({
      bridgeKey: "bridge-a",
      projectId: "project-a",
      canvasId: "canvas-a",
      result: {
        applied: 0,
        openedUiActions: 0,
        createdNodeIds: [],
        errors: [
          "envelopes[0].commands[0]: edge output role planning_text is not accepted by target imageGenNode for link_type prompt_for. Expected source role input_text.",
        ],
        commandResults: [
          {
            commandIndex: -1,
            type: "validate",
            status: "error",
            label: "校验画布命令",
            error:
              "edge output role planning_text is not accepted by target imageGenNode for link_type prompt_for. Expected source role input_text.",
          },
        ],
      },
    });

    expect(payload.user_message).toBe("当前文本需要先作为生成提示词连接到图片节点，我会按可执行的提示词来源来处理。");
    expect(payload.agent_hint).toContain("Do not mention");
    expect(payload.agent_hint).toContain("prompt_for");
    expect(payload.message).toBe(payload.user_message);
    expect(payload.errors.join("\n")).toContain("planning_text");
    expect(payload.user_message).not.toContain("planning_text");
    expect(payload.user_message).not.toContain("input_text");
    expect(payload.user_message).not.toContain("prompt_for");
  });

  it("keeps structured multiple-choice answers in bridge payload", () => {
    const payload = buildSkillStudioQuestionToolResultForTest(
      {
        type: "skill_studio.questions",
        bridge_key: "skill-key-2",
        questions: [
          {
            id: "content",
            title: "内容元素？",
            selection_mode: "multiple",
            options: [
              { id: "photo", label: "特色图片" },
              { id: "qr", label: "二维码/Logo" },
            ],
          },
        ],
      },
      {
        content: {
          option_ids: ["photo", "qr"],
          custom_text: "需要留一个主标题位置",
        },
      },
    );

    expect(payload.selections).toEqual({
      content: {
        option_ids: ["photo", "qr"],
        custom_text: "需要留一个主标题位置",
      },
    });
    expect(payload.message).toContain("内容元素？：特色图片；二维码/Logo；补充：需要留一个主标题位置");
  });
});

describe("Assistant clarification response", () => {
  it("builds a reusable clarification summary from selected answers", () => {
    const text = buildAssistantClarificationResponseForTest(
      {
        type: "assistant.clarification.request",
        clarification_id: "clarify_01",
        title: "向用户提问",
        questions: [
          {
            id: "skill_kind",
            title: "你想创建的 skill 是做什么的？",
            options: [
              { id: "workflow", label: "工作流自动化" },
              { id: "domain", label: "领域知识" },
            ],
          },
          {
            id: "scope",
            title: "这个 skill 的使用范围是？",
            options: [
              { id: "user", label: "用户级（推荐）" },
              { id: "project", label: "项目级" },
            ],
          },
        ],
      },
      {
        skill_kind: { option_ids: ["workflow"], custom_text: "用于海报生成" },
        scope: { option_ids: ["user"], custom_text: "" },
      },
    );

    expect(text).toContain("你想创建的 skill 是做什么的？\n工作流自动化；补充：用于海报生成");
    expect(text).toContain("这个 skill 的使用范围是？\n用户级（推荐）");
  });

  it("builds a generic bridge tool result payload", () => {
    const payload = buildAssistantClarificationToolResultForTest(
      {
        type: "assistant.clarification.request",
        bridge_key: "clarify-key-1",
        project_id: "project-a",
        canvas_id: "canvas-a",
        agent_id: "agent-1",
        turn_id: "turn-a",
        clarification_id: "clarify_01",
        questions: [
          {
            id: "skill_kind",
            title: "你想创建的 skill 是做什么的？",
            options: [{ id: "workflow", label: "工作流自动化" }],
          },
        ],
      },
      {
        skill_kind: { option_ids: ["workflow"], custom_text: "" },
      },
    );

    expect(payload).toMatchObject({
      bridge_key: "clarify-key-1",
      project_id: "project-a",
      canvas_id: "canvas-a",
      agent_id: "agent-1",
      turn_id: "turn-a",
      tool_call_status: "completed",
      clarification_status: "answered",
      action: "submit",
      answers: {
        skill_kind: { option_ids: ["workflow"], custom_text: "" },
      },
      ok: true,
    });
    expect(payload.message).toContain("你想创建的 skill 是做什么的？");
  });
});

describe("Skill Studio status events", () => {
  it("marks assistant messages with a status event as Skill Studio UI", () => {
    expect(messageHasSkillStudioUiEventForTest({
      id: "assistant-turn-1",
      role: "assistant",
      text: "",
      timestamp: 10,
      turnId: "turn-1",
      uiEvents: [
        {
          type: "skill_studio.status",
          status: "routing",
          message: "正在进入 Skill Studio...",
        },
      ],
    })).toBe(true);
  });

  it("hides stale status once an interactive Skill Studio card is present", () => {
    expect(skillStudioEventsFromUiEventsForTest([
      {
        type: "skill_studio.status",
        status: "routing",
        message: "正在进入 Skill Studio...",
      },
      {
        type: "skill_studio.questions",
        skill_studio_session_id: "skill_studio_01",
        questions: [],
      },
    ]).map((event) => event.type)).toEqual(["skill_studio.questions"]);
  });

  it("merges repeated Skill Studio question events into the latest state", () => {
    const events = skillStudioEventsFromUiEventsForTest([
      {
        type: "skill_studio.questions",
        bridge_key: "skill-key-1",
        skill_studio_session_id: "studio-1",
        questions: [],
      },
      {
        type: "skill_studio.questions",
        bridge_key: "skill-key-1",
        skill_studio_session_id: "studio-1",
        submitted: true,
        action: "submit",
        selections: { audience: "locals" },
      },
    ]);

    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      type: "skill_studio.questions",
      bridge_key: "skill-key-1",
      submitted: true,
      selections: { audience: "locals" },
    });
  });

  it("merges repeated Skill Studio draft events into the latest draft state", () => {
    const events = skillStudioEventsFromUiEventsForTest([
      {
        type: "skill_studio.draft",
        bridge_key: "draft-key-1",
        skill_studio_session_id: "studio-1",
        skill: { id: "original-skill" },
      },
      {
        type: "skill_studio.draft",
        bridge_key: "draft-key-1",
        skill_studio_session_id: "studio-1",
        draft: { skill: { id: "edited-skill" }, recipes: [] },
      },
      {
        type: "skill_studio.draft",
        bridge_key: "draft-key-1",
        skill_studio_session_id: "studio-1",
        submitted: true,
        draft: { skill: { id: "submitted-skill" }, recipes: [] },
      },
    ]);

    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      type: "skill_studio.draft",
      bridge_key: "draft-key-1",
      submitted: true,
      draft: { skill: { id: "submitted-skill" } },
    });
  });

  it("hides routing status once assistant prose has started", () => {
    expect(visibleSkillStudioEventsForMessageForTest({
      id: "assistant-turn-1",
      role: "assistant",
      text: "我正在查看可用 Skill。",
      timestamp: 10,
      turnId: "turn-1",
      uiEvents: [
        {
          type: "skill_studio.status",
          status: "routing",
          message: "正在进入 Skill Studio...",
        },
      ],
    }).map((event) => event.type)).toEqual([]);
  });

  it("hides routing status once an assistant clarification card is visible", () => {
    expect(visibleSkillStudioEventsForMessageForTest({
      id: "assistant-turn-1",
      role: "assistant",
      text: "",
      timestamp: 10,
      turnId: "turn-1",
      uiEvents: [
        {
          type: "skill_studio.status",
          status: "routing",
          message: "正在进入 Skill Studio...",
        },
        {
          type: "assistant.clarification.request",
          bridge_key: "clarify-key-1",
          title: "家乡文化短片 Skill 配置",
          submitted: true,
          action: "submit",
          questions: [],
          answers: {},
        },
      ],
    }).map((event) => event.type)).toEqual([]);
  });

  it("hides status-only Skill Studio messages once the same turn has a submitted card", () => {
    const statusOnly = message("assistant-status", "assistant", "", 10, "turn-1");
    statusOnly.uiEvents = [
      {
        type: "skill_studio.status",
        status: "routing",
        message: "正在进入 Skill Studio...",
      },
    ];

    expect(shouldHideSkillStudioStatusOnlyMessageForTest(statusOnly, new Set(["turn-1"]))).toBe(true);
    expect(shouldHideSkillStudioStatusOnlyMessageForTest(statusOnly, new Set(["turn-2"]))).toBe(false);
  });

  it("hides canvas context reads once a Skill Studio card is available", () => {
    const assistant = message("assistant-turn-1", "assistant", "", 10, "turn-1");
    assistant.uiEvents = [
      {
        type: "skill_studio.draft",
        skill_studio_session_id: "studio-1",
        draft: { skill: { id: "home-culture" }, recipes: [] },
      },
    ];

    const visible = visibleCanvasContextActivitiesForMessageForTest(assistant, [
      {
        key: "context:node-params",
        turnId: "turn-1",
        bridgeKey: "node-params",
        status: "done",
        labels: ["节点参数"],
        errors: [],
      },
      {
        key: "context:validate",
        turnId: "turn-1",
        bridgeKey: "validate",
        status: "done",
        labels: ["命令校验"],
        errors: [],
      },
    ]);

    expect(visible.map((activity) => activity.key)).toEqual(["context:validate"]);
  });
});

describe("Skill Studio draft response", () => {
  it("uses the same Chinese field names as the catalog edit pages", () => {
    expect(skillStudioDraftFieldLabelsForTest.skill).toMatchObject({
      keywords: "触发关键词",
      nodeTypes: "节点类型",
      metaPlanningHints: "规划器提示词",
      promptStyleGuide: "风格指引",
      behaviorRules: "行为规则",
      passingScore: "通过分数线",
      domainRules: "领域规则",
    });
    expect(skillStudioDraftFieldLabelsForTest.recipe).toMatchObject({
      output_kind: "生成类型",
      action_keys: "操作类型",
      systemPrompt: "System Prompt",
      required_elements: "必需元素",
      planner_cue: "规划器提示词",
      output_summary: "输出概述",
    });
  });

  it("builds a bridge tool result with the edited draft payload", () => {
    const event = {
      type: "skill_studio.draft" as const,
      bridge_key: "skill-key-2",
      project_id: "project-a",
      canvas_id: "canvas-a",
      agent_id: "agent-1",
      turn_id: "turn-a",
      skill_studio_session_id: "skill_studio_01",
      summary: "草稿摘要",
      skill: {
        id: "home-culture-poster",
        description: "家乡文化海报",
        category: "social",
        planning: {
          metaPlanningHints: "先识别地域符号",
        },
      },
      recipes: [
        {
          id: "home-culture-poster-image",
          name: "家乡文化海报出图",
          output_kind: "image",
          systemPrompt: "生成海报",
          required_elements: ["地域符号"],
        },
      ],
    };

    const payload = buildSkillStudioDraftToolResultForTest(event, {
      skill: event.skill,
      recipes: event.recipes,
      summary: event.summary,
    });

    expect(payload).toMatchObject({
      bridge_key: "skill-key-2",
      project_id: "project-a",
      canvas_id: "canvas-a",
      agent_id: "agent-1",
      turn_id: "turn-a",
      action: "confirm_add",
      skill_studio_status: "catalog_saved",
      saved_to_catalog: true,
      saved_skill_ids: ["home-culture-poster"],
      saved_recipe_ids: ["home-culture-poster-image"],
      draft: {
        skill: {
          id: "home-culture-poster",
          planning: {
            metaPlanningHints: "先识别地域符号",
          },
        },
        recipes: [
          {
            id: "home-culture-poster-image",
            required_elements: ["地域符号"],
          },
        ],
      },
    });
    expect(payload.message).toContain("home-culture-poster");
    expect(payload.message).toContain("已保存为正式 Skill / Recipe");
  });

  it("builds a bridge tool result when the draft is cancelled", () => {
    const event = {
      type: "skill_studio.draft" as const,
      bridge_key: "skill-key-2",
      project_id: "project-a",
      canvas_id: "canvas-a",
      agent_id: "agent-1",
      turn_id: "turn-a",
      skill_studio_session_id: "skill_studio_01",
      draft: { skill: { id: "home-culture-poster" }, recipes: [] },
    };

    const payload = buildSkillStudioDraftCancelToolResultForTest(event);

    expect(payload).toMatchObject({
      bridge_key: "skill-key-2",
      project_id: "project-a",
      canvas_id: "canvas-a",
      agent_id: "agent-1",
      turn_id: "turn-a",
      action: "cancel",
      skill_studio_status: "catalog_cancelled",
      cancelled: true,
      saved_to_catalog: false,
      saved_skill_ids: [],
      saved_recipe_ids: [],
    });
    expect(payload.message).toContain("用户已取消 Skill Studio 草稿保存");
    expect(payload.message).toContain("本次草稿不会写入虾画配置");
    expect(payload.message).toContain("不要自动继续创建画布");
    expect(payload.message).not.toContain("继续回复");
  });

  it("normalizes the draft into catalog payloads before saving", () => {
    const items = buildSkillStudioCatalogSaveItemsForTest({
      skill: {
        id: "home-culture-poster",
        description: "家乡文化海报",
        category: "social",
        triggers: {
          keywords: ["家乡文化"],
          nodeTypes: ["imageGeneration"],
        },
        planning: {
          metaPlanningHints: "先识别地域符号",
          promptStyleGuide: "水墨写意",
          behaviorRules: ["保持文化准确"],
        },
        evaluation: {
          scoreAnchors: [{ score: 8, description: "文化符号明确" }],
          passingScore: 7,
          domainRules: ["不得混用地域符号"],
          visual: {
            dimensions: [{ name: "文化识别度", weight: 0.6, description: "能看出地域特征" }],
          },
          text: {
            dimensions: [{ name: "文案清晰度", weight: 0.4, description: "文案简洁" }],
          },
        },
      },
      recipes: [
        {
          id: "home-culture-poster-image",
          name: "家乡文化海报出图",
          output_kind: "image",
          action_keys: ["home-culture-poster-image"],
          systemPrompt: "生成海报",
          required_elements: ["地域符号"],
          planner_cue: "根据地域符号生成海报",
          output_summary: "一张家乡文化海报",
          needs_multimodal_input: true,
        },
      ],
    });

    expect(items).toEqual([
      expect.objectContaining({
        kind: "skills",
        payload: expect.objectContaining({
          id: "home-culture-poster",
          enabled: true,
          triggers: {
            keywords: ["家乡文化"],
            node_scopes: ["imageGeneration"],
          },
          planning: expect.objectContaining({
            planning_notes: "先识别地域符号",
            prompt_guide: "水墨写意",
            conduct_rules: ["保持文化准确"],
          }),
          evaluation: expect.objectContaining({
            quality_threshold: 7,
            domain_constraints: ["不得混用地域符号"],
            rating_bands: [{ score: 8, description: "文化符号明确" }],
            visual_review_items: [
              { name: "文化识别度", weight: 0.6, description: "能看出地域特征" },
            ],
            text_review_items: [
              { name: "文案清晰度", weight: 0.4, description: "文案简洁" },
            ],
          }),
        }),
      }),
      expect.objectContaining({
        kind: "recipes",
        payload: expect.objectContaining({
          id: "home-culture-poster-image",
          output_kind: "image",
          action_keys: ["home-culture-poster-image"],
          system_prompt: "生成海报",
          must_have_items: ["地域符号"],
          planning_prompt: "根据地域符号生成海报",
          result_summary: "一张家乡文化海报",
          requires_source_media: true,
        }),
      }),
    ]);
  });
});

describe("Skill Studio flow ordering", () => {
  it("renders anchored cards at the text position where the event arrived", () => {
    const items = buildSkillStudioFlowItemsForTest(
      "先说明。\n后续文字。",
      [
        {
          type: "skill_studio.draft",
          anchor_text_prefix: "先说明。\n",
          skill_studio_session_id: "skill_studio_01",
          skill: { id: "poster-skill" },
          recipes: [],
        },
      ],
    );

    expect(items.map((item) => item.kind)).toEqual(["text", "event", "text"]);
    expect(items[0]).toMatchObject({ kind: "text", text: "先说明。\n" });
    expect(items[2]).toMatchObject({ kind: "text", text: "后续文字。" });
  });

  it("keeps previously anchored cards before continuation text when streaming restarts after a tool result", () => {
    const items = buildSkillStudioFlowItemsForTest(
      "已保存这个 Skill，接下来可以继续扩展。",
      [
        {
          type: "skill_studio.draft",
          anchor_text_prefix: "Here's the complete Skill and Recipe draft:",
          skill_studio_session_id: "skill_studio_01",
          skill: { id: "poster-skill" },
          recipes: [],
        },
      ],
    );

    expect(items.map((item) => item.kind)).toEqual(["event", "text"]);
    expect(items[1]).toMatchObject({ kind: "text", text: "已保存这个 Skill，接下来可以继续扩展。" });
  });

  it("keeps submitted unanchored question cards before continuation text", () => {
    const items = buildSkillStudioFlowItemsForTest(
      "我会根据你的选择生成草稿。",
      [
        {
          type: "skill_studio.questions",
          submitted: true,
          skill_studio_session_id: "skill_studio_01",
          selections: { audience: "young" },
          questions: [],
        },
      ],
    );

    expect(items.map((item) => item.kind)).toEqual(["event", "text"]);
  });

  it("keeps cancelled draft cards before continuation text", () => {
    const items = buildSkillStudioFlowItemsForTest(
      "已取消保存，我会继续按当前上下文回复。",
      [
        {
          type: "skill_studio.draft",
          cancelled: true,
          skill_studio_session_id: "skill_studio_01",
          skill: { id: "poster-skill" },
          recipes: [],
        },
      ],
    );

    expect(items.map((item) => item.kind)).toEqual(["event", "text"]);
    expect(items[1]).toMatchObject({ kind: "text", text: "已取消保存，我会继续按当前上下文回复。" });
  });
});

describe("Freezone chat scope", () => {
  it("keeps different Freezone canvases in separate local session buckets", () => {
    const canvasA = scopeForProjectForTest("project-a", "freezone", "canvas-a");
    const canvasB = scopeForProjectForTest("project-a", "freezone", "canvas-b");

    expect(canvasA).toMatchObject({
      kind: "project",
      id: "project-a",
      surface: "freezone",
      canvasId: "canvas-a",
    });
    expect(scopeSessionKeyForTest(canvasA)).toBe(
      "supertale:project:project-a:freezone:canvas-a:agent:main",
    );
    expect(scopeSessionKeyForTest(canvasB)).toBe(
      "supertale:project:project-a:freezone:canvas-b:agent:main",
    );
  });

  it("keeps different Freezone agents on the same canvas in separate local session buckets", () => {
    const agentA = scopeForProjectForTest("project-a", "freezone", "canvas-a", "main");
    const agentB = scopeForProjectForTest("project-a", "freezone", "canvas-a", "agent-2");

    expect(agentA).toMatchObject({
      kind: "project",
      id: "project-a",
      surface: "freezone",
      canvasId: "canvas-a",
      agentId: "main",
    });
    expect(scopeSessionKeyForTest(agentA)).toBe(
      "supertale:project:project-a:freezone:canvas-a:agent:main",
    );
    expect(scopeSessionKeyForTest(agentB)).toBe(
      "supertale:project:project-a:freezone:canvas-a:agent:agent-2",
    );
  });

  it("does not let agent ids affect director chat scopes", () => {
    const director = scopeForProjectForTest("project-a", "director", null, "agent-2");

    expect(director).toEqual({
      kind: "project",
      id: "project-a",
      surface: "director",
      canvasId: null,
    });
    expect(scopeSessionKeyForTest(director)).toBe("supertale:project:project-a:director");
  });
});

describe("useSuperChat websocket lifecycle", () => {
  const OriginalWebSocket = globalThis.WebSocket;

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    Object.defineProperty(globalThis, "WebSocket", {
      value: OriginalWebSocket,
      writable: true,
      configurable: true,
    });
  });

  it("does not open a websocket while the panel connection is disabled", () => {
    vi.useFakeTimers();
    const sockets: unknown[] = [];
    class TestWebSocket {
      static OPEN = 1;
      readyState = 0;
      onopen: (() => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onerror: (() => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;

      constructor() {
        sockets.push(this);
      }

      send() {}
      close() {}
    }
    Object.defineProperty(globalThis, "WebSocket", {
      value: TestWebSocket,
      writable: true,
      configurable: true,
    });

    renderHook(() =>
      useSuperChat({
        project: "project-a",
        displayName: "Tester",
        surface: "freezone",
        freezoneCanvasId: "canvas-a",
        freezoneAgentId: "agent-2",
        connectionEnabled: false,
      }),
    );

    act(() => {
      vi.advanceTimersByTime(100);
    });

    expect(sockets).toHaveLength(0);
  });
});

describe("canvas command bridge events", () => {
  it("passes the current assistant text as the canvas command anchor", () => {
    const received: unknown[] = [];
    const handleEvent = (event: Event) => {
      received.push((event as CustomEvent).detail);
    };
    window.addEventListener(SUPERCHAT_CANVAS_COMMAND_EVENT, handleEvent);

    try {
      dispatchCanvasCommandFrameForTest(
        {
          type: "canvas.command",
          turn_id: "turn-a",
          bridge_key: "bridge-a",
          canvas_id: "canvas-a",
          envelope: { schema_version: "canvas_chat_commands.v1", commands: [] },
        },
        "正在更新视频节点的内容...\n",
      );
    } finally {
      window.removeEventListener(SUPERCHAT_CANVAS_COMMAND_EVENT, handleEvent);
    }

    expect(received).toHaveLength(1);
    expect(received[0]).toMatchObject({
      anchorTextPrefix: "正在更新视频节点的内容...\n",
      frame: {
        type: "canvas.command",
        bridge_key: "bridge-a",
      },
    });
  });
});

describe("canvas context bridge results", () => {
  it("preserves canvas_context_status in the websocket frame", () => {
    const frame = canvasContextToolResultFrameForTest({
      type: "canvas.context.result",
      turn_id: "turn-a",
      bridge_key: "bridge-a",
      project_id: "project-a",
      canvas_id: "canvas-a",
      tool_call_status: "completed",
      canvas_context_status: "resolved",
      ok: true,
      responses: [],
      errors: [],
      message: "ok",
    });

    expect(frame).toMatchObject({
      type: "canvas.context.result",
      canvas_context_status: "resolved",
    });
  });
});

describe("sanitizeMessagesForCache", () => {
  it("strips attachment inline content but keeps metadata and raw", () => {
    const original: ChatMessage = {
      id: "m1",
      role: "user",
      text: "见图",
      timestamp: 1,
      raw: { keep: "me" },
      attachments: [
        {
          fileName: "a.png",
          mimeType: "image/png",
          fileSize: 1234,
          url: "https://example/a.png",
          path: "/a.png",
          content: "data:image/png;base64,AAAA",
        },
      ],
    };

    const [sanitized] = sanitizeMessagesForCache([original]);

    expect(sanitized.attachments?.[0].content).toBeUndefined();
    expect(sanitized.attachments?.[0].fileName).toBe("a.png");
    expect(sanitized.attachments?.[0].url).toBe("https://example/a.png");
    expect(sanitized.raw).toEqual({ keep: "me" });
    // The original message must not be mutated.
    expect(original.attachments?.[0].content).toBe("data:image/png;base64,AAAA");
  });

  it("leaves messages without attachments or raw untouched", () => {
    const original: ChatMessage = { id: "m1", role: "user", text: "hi", timestamp: 1 };
    expect(sanitizeMessagesForCache([original])[0]).toBe(original);
  });

  it("de-nests raw so it can't grow across load→save cycles", () => {
    // After one round-trip, normalizeMessage stores the prior normalized
    // message under raw — which itself carries a raw field. Caching must drop
    // that inner raw so depth never exceeds 1.
    const serverPayload = { content: "<ui-spec>{}</ui-spec>" };
    const roundTripped: ChatMessage = {
      id: "m1",
      role: "assistant",
      text: "hi",
      timestamp: 1,
      raw: { id: "m1", role: "assistant", text: "hi", raw: serverPayload },
    };

    const [sanitized] = sanitizeMessagesForCache([roundTripped]);
    const raw = sanitized.raw as Record<string, unknown>;

    expect("raw" in raw).toBe(false);
    expect(raw.text).toBe("hi");
    // Re-sanitizing stays flat (stable fixpoint, no unbounded growth).
    const reSanitized = sanitizeMessagesForCache([
      { ...sanitized, raw: { ...raw, raw: serverPayload } },
    ]);
    expect("raw" in (reSanitized[0].raw as Record<string, unknown>)).toBe(false);
  });
});

describe("pruneOldMessageCaches", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("removes expired, legacy, and malformed caches but keeps fresh ones", () => {
    const now = 10 * DAY_MS;
    localStorage.setItem(
      `${MESSAGE_CACHE_PREFIX}fresh`,
      JSON.stringify({ updatedAt: now - DAY_MS, messages: [] }),
    );
    localStorage.setItem(
      `${MESSAGE_CACHE_PREFIX}stale`,
      JSON.stringify({ updatedAt: now - 8 * DAY_MS, messages: [] }),
    );
    // Legacy bare-array format has no updatedAt → reclaimed.
    localStorage.setItem(`${MESSAGE_CACHE_PREFIX}legacy`, JSON.stringify([{ id: "x" }]));
    localStorage.setItem(`${MESSAGE_CACHE_PREFIX}broken`, "{not json");
    localStorage.setItem("unrelated:key", "keep-me");

    pruneOldMessageCaches(now);

    expect(localStorage.getItem(`${MESSAGE_CACHE_PREFIX}fresh`)).not.toBeNull();
    expect(localStorage.getItem(`${MESSAGE_CACHE_PREFIX}stale`)).toBeNull();
    expect(localStorage.getItem(`${MESSAGE_CACHE_PREFIX}legacy`)).toBeNull();
    expect(localStorage.getItem(`${MESSAGE_CACHE_PREFIX}broken`)).toBeNull();
    expect(localStorage.getItem("unrelated:key")).toBe("keep-me");
  });

  it("reclaims caches with a future timestamp (clock skew / corruption)", () => {
    const now = 10 * DAY_MS;
    localStorage.setItem(
      `${MESSAGE_CACHE_PREFIX}future`,
      JSON.stringify({ updatedAt: now + DAY_MS, messages: [] }),
    );
    pruneOldMessageCaches(now);
    expect(localStorage.getItem(`${MESSAGE_CACHE_PREFIX}future`)).toBeNull();
  });
});
