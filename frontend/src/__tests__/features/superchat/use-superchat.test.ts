// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { normalizeMessage } from "@/features/superchat/message";
import {
  SUPERCHAT_CANVAS_COMMAND_EVENT,
  canvasContextToolResultFrameForTest,
  dispatchCanvasCommandFrameForTest,
  mergeHistorySnapshot,
  pruneOldMessageCaches,
  sanitizeMessagesForCache,
  scopeForProjectForTest,
  scopeSessionKeyForTest,
  useSuperChat,
} from "@/features/superchat/use-superchat";
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
