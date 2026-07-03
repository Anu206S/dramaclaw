import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { buildCanvasOntologyContext } from "@/features/canvas/ontology/canvasOntology";
import { SuperChatPanel } from "@/features/superchat/superchat-panel";
import type { CanvasNode } from "@/features/canvas/domain/canvasNodes";
import {
  buildCanvasNodeReferenceAttachment,
  canvasNodeReferenceAttachmentNodes,
  isCanvasNodeReferenceAttachment,
} from "@/features/freezone/chatNodeReferences";
import type { ChatAttachment, ChatMessage } from "@/features/superchat/types";
import { useCanvasStore } from "@/stores/canvasStore";

const superChatMocks = vi.hoisted(() => ({
  send: vi.fn(async () => true),
  messages: [] as ChatMessage[],
  busy: false,
  showToolEvents: false,
}));

const apiMocks = vi.hoisted(() => ({
  post: vi.fn(() => ({ catch: vi.fn() })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) => {
      const translations: Record<string, string> = {
        "aiAssistant.placeholder": "写下灵感、剧情或任务，虾导来接住",
        "aiAssistant.freezonePlaceholder": "想画什么、改哪里，直接告诉虾画",
        "aiAssistant.canvasReferenceOnlyPrompt": "请基于当前选中的画布节点继续。",
        "aiAssistant.send": "发送",
        "aiAssistant.queuedCount": "待发送 {{count}} 条",
        "freezone.chat.currentSelection": "当前选中",
        "freezone.chat.usedThisTurn": "本轮会使用",
        "freezone.chat.canvasCommandsCancelled": "已取消画布操作",
      };
      return (translations[key] ?? key).replace("{{count}}", String(options?.count ?? ""));
    },
  }),
}));

vi.mock("@tanstack/react-router", () => ({
  useParams: () => ({ project: "project-a" }),
}));

vi.mock("@/task-center/event-bus-context", () => ({
  useEventBus: () => ({
    on: vi.fn(() => vi.fn()),
  }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    post: apiMocks.post,
  },
}));

vi.mock("@/api/projects", () => ({
  listCharacters: vi.fn(async () => []),
  listFreezoneProjectAssets: vi.fn(async () => []),
}));

vi.mock("border-beam-vanilla", () => ({
  attachBorderBeam: () => ({ destroy: vi.fn() }),
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("dramaclaw-spec-render", () => ({
  SpecRenderer: () => null,
  SpecRendererProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  VideoDetailModal: () => null,
}));

vi.mock("@/features/superchat/use-superchat", () => ({
  SUPERCHAT_CANVAS_COMMAND_EVENT: "superchat/canvas-command",
  SUPERCHAT_CANVAS_CONTEXT_REQUEST_EVENT: "superchat/canvas-context-request",
  useSuperChat: () => ({
    abort: vi.fn(),
    approvals: [],
    activeTurnId: null,
    busy: superChatMocks.busy,
    connected: true,
    connecting: false,
    error: null,
    activeModel: null,
    clearPinned: vi.fn(),
    deleteMessage: vi.fn(),
    deletedIds: new Set<string>(),
    historyHasMore: false,
    historyLoadingOlder: false,
    historyReady: true,
    loadOlderHistory: vi.fn(),
    messages: superChatMocks.messages,
    models: [],
    modelsLoading: false,
    requestHistory: vi.fn(),
    refreshModels: vi.fn(),
    refreshRelayInstances: vi.fn(),
    relayInstances: [],
    resolveApproval: vi.fn(),
    selectRelayInstance: vi.fn(),
    send: superChatMocks.send,
    selectedInstanceId: "",
    sessionControl: vi.fn(),
    setSettings: vi.fn(),
    settings: {
      showToolEvents: superChatMocks.showToolEvents,
      showStructuredSourceWhileStreaming: false,
      uploadTarget: "openclaw",
    },
    pinnedIds: new Set<string>(),
    streamText: "",
    switchModel: vi.fn(),
    togglePin: vi.fn(),
  }),
}));

describe("SuperChatPanel Freezone selection attachment state", () => {
  beforeAll(() => {
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: vi.fn(() => true),
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    superChatMocks.send.mockClear();
    superChatMocks.messages = [];
    superChatMocks.busy = false;
    superChatMocks.showToolEvents = false;
    apiMocks.post.mockClear();
    useCanvasStore.getState().setCanvasData([], []);
    useCanvasStore.getState().setSelectedNode(null);
  });

  it("uses the dedicated Xia Draw placeholder in freezone mode", () => {
    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    expect(screen.getByPlaceholderText("想画什么、改哪里，直接告诉虾画")).toBeInTheDocument();
  });

  it("does not show a selected canvas node as current-turn context after its attachment was consumed", () => {
    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[
          {
            nodeId: "image-node-1",
            nodeType: "imageNode",
            label: "图片节点",
          },
        ]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    expect(screen.queryByText("本轮会使用")).not.toBeInTheDocument();
    expect(screen.queryByText("图片节点")).not.toBeInTheDocument();
  });

  it("lets the user remove a selected canvas node from current-turn context", () => {
    const node = {
      id: "image-node-1",
      type: "imageNode",
      position: { x: 0, y: 0 },
      selected: true,
      data: {
        title: "图片节点",
      },
    } satisfies Partial<CanvasNode> as CanvasNode;

    useCanvasStore.getState().setCanvasData([node], []);
    useCanvasStore.getState().setSelectedNode(node.id);

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [node.id],
        })}
        pendingAttachments={[]}
      />,
    );

    expect(screen.getByText("本轮会使用")).toBeInTheDocument();

    const removeButton = screen.getByLabelText("移除画布引用");
    expect(removeButton).toHaveClass("opacity-0");
    expect(removeButton).toHaveClass("group-hover:opacity-100");

    fireEvent.click(removeButton);

    expect(screen.queryByText("本轮会使用")).not.toBeInTheDocument();
    expect(useCanvasStore.getState().nodes[0]?.selected).toBe(false);
    expect(useCanvasStore.getState().selectedNodeId).toBeNull();
  });

  it("lets the user remove all selected canvas nodes from current-turn context", () => {
    const nodes = [
      {
        id: "image-node-1",
        type: "imageNode",
        position: { x: 0, y: 0 },
        selected: true,
        data: { title: "图片节点 A" },
      },
      {
        id: "image-node-2",
        type: "imageNode",
        position: { x: 220, y: 0 },
        selected: true,
        data: { title: "图片节点 B" },
      },
    ] satisfies Partial<CanvasNode>[] as CanvasNode[];

    useCanvasStore.getState().setCanvasData(nodes, []);
    useCanvasStore.getState().setSelectedNode(nodes[0].id);

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: nodes.map((node) => node.id),
        })}
        pendingAttachments={[]}
      />,
    );

    expect(screen.getByText("本轮会使用")).toBeInTheDocument();
    expect(screen.getByText("全部取消")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("取消全部画布引用"));

    expect(screen.queryByText("本轮会使用")).not.toBeInTheDocument();
    expect(useCanvasStore.getState().nodes.every((node) => !node.selected)).toBe(true);
    expect(useCanvasStore.getState().selectedNodeId).toBeNull();
  });

  it("does not duplicate canvas references between attachments and current selection", async () => {
    const node = {
      id: "image-node-1",
      type: "imageNode",
      position: { x: 0, y: 0 },
      selected: true,
      data: {
        displayName: "图片节点",
      },
    } satisfies Partial<CanvasNode> as CanvasNode;
    const attachment = buildCanvasNodeReferenceAttachment(
      "project-a",
      "canvas-a",
      [node],
      [],
      [node],
      { displayNodes: [node] },
    );
    expect(attachment).not.toBeNull();

    useCanvasStore.getState().setCanvasData([node], []);
    useCanvasStore.getState().setSelectedNode(node.id);

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([node], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [node.id],
        })}
        pendingAttachments={[attachment as ChatAttachment]}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getAllByRole("button", { name: /图片节点 · image-node-1/ })).toHaveLength(1);
    expect(screen.getAllByLabelText("移除画布引用")).toHaveLength(1);
    expect(screen.getByText("本轮会使用")).toBeInTheDocument();
  });

  it("sends selected canvas nodes as canvas reference attachments", async () => {
    const node = {
      id: "image-node-1",
      type: "imageNode",
      position: { x: 0, y: 0 },
      selected: true,
      data: {
        title: "图片节点",
        imageUrl: "https://example.test/image.png",
      },
    } satisfies Partial<CanvasNode> as CanvasNode;

    useCanvasStore.getState().setCanvasData([node], []);
    useCanvasStore.getState().setSelectedNode(node.id);

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([node], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [node.id],
        })}
        pendingAttachments={[]}
      />,
    );

    fireEvent.click(screen.getByLabelText("发送"));

    await waitFor(() => expect(superChatMocks.send).toHaveBeenCalledTimes(1));

    const [text, attachments, transportText] = superChatMocks.send.mock.calls[0] as unknown as [
      string,
      ChatAttachment[],
      string,
    ];
    expect(text).toBe("请基于当前选中的画布节点继续。");
    expect(attachments).toHaveLength(1);
    expect(isCanvasNodeReferenceAttachment(attachments[0])).toBe(true);
    expect(canvasNodeReferenceAttachmentNodes(attachments[0])).toEqual(expect.arrayContaining([
      expect.objectContaining({
        nodeId: node.id,
      }),
    ]));
    expect(transportText).toContain("[SUPERTALE_CANVAS_NODE_REFERENCES]");
    expect(useCanvasStore.getState().nodes[0]?.selected).toBe(false);
  });

  it("renders sent canvas references as node cards instead of ordinary attachment chips", () => {
    const node = {
      id: "image-node-1",
      type: "imageNode",
      position: { x: 0, y: 0 },
      selected: false,
      data: {
        imageUrl: "https://example.test/image.png",
      },
    } satisfies Partial<CanvasNode> as CanvasNode;
    const attachment = buildCanvasNodeReferenceAttachment(
      "project-a",
      "canvas-a",
      [node],
      [],
      [node],
      { displayNodes: [node] },
    );
    expect(attachment).not.toBeNull();
    superChatMocks.messages = [
      {
        id: "message-a",
        role: "user",
        text: "你好",
        displayName: "User",
        timestamp: Date.now(),
        attachments: [attachment as ChatAttachment],
      },
    ];
    useCanvasStore.getState().setCanvasData([node], []);

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([node], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    expect(screen.getByTitle(/image-node-1/)).toHaveClass("group/canvas-ref");
  });

  it("clears local queued messages when switching freezone canvas scope", () => {
    superChatMocks.busy = true;
    const { rerender } = render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    const input = screen.getByPlaceholderText("想画什么、改哪里，直接告诉虾画");
    fireEvent.change(input, { target: { value: "帮我加个视频节点" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.getByText("待发送 1 条")).toBeInTheDocument();

    rerender(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-b"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-b",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    expect(screen.queryByText("待发送 1 条")).not.toBeInTheDocument();
    expect(superChatMocks.send).not.toHaveBeenCalled();
  });

  it("keeps user message actions inside the bubble and copies with the legacy clipboard fallback", () => {
    superChatMocks.messages = [
      {
        id: "message-a",
        role: "user",
        text: "你好",
        displayName: "User",
        timestamp: Date.now(),
        attachments: [],
      },
    ];

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    const copyButton = screen.getByLabelText("Copy");
    expect(copyButton.parentElement).toHaveClass("absolute");
    expect(copyButton.parentElement).toHaveClass("right-1.5");

    fireEvent.click(copyButton);

    expect(document.execCommand).toHaveBeenCalledWith("copy");
  });

  it("resolves frontend canvas context requests and shows activity status", async () => {
    superChatMocks.messages = [
      {
        id: "assistant-a",
        role: "assistant",
        text: "我来检查当前画布状态：",
        displayName: "Agent",
        timestamp: Date.now(),
        turnId: "turn-a",
        attachments: [],
      },
    ];

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    act(() => {
      window.dispatchEvent(new CustomEvent("superchat/canvas-context-request", {
        detail: {
          bridge_key: "bridge-a",
          canvas_id: "canvas-a",
          turn_id: "turn-a",
          envelope: {
            schema_version: "canvas_context_request.v1",
            requests: [{ type: "canvas_ontology" }],
          },
        },
      }));
    });

    expect(await screen.findByText("正在读取画布 Ontology")).toBeInTheDocument();

    act(() => {
      window.dispatchEvent(new CustomEvent("freezone/canvas-context-tool-result", {
        detail: {
          type: "canvas.context.result",
          turn_id: "turn-a",
          bridge_key: "bridge-a",
          project_id: "project-a",
          canvas_id: "canvas-a",
          tool_call_status: "completed",
          canvas_context_status: "resolved",
          ok: true,
          responses: [{ type: "canvas_ontology", data: {} }],
          errors: [],
          message: "Frontend returned requested canvas context.",
        },
      }));
    });

    await waitFor(() => expect(screen.getByText("已读取画布 Ontology")).toBeInTheDocument());
  });

  it("persists and reports approved canvas command results", async () => {
    superChatMocks.messages = [
      {
        id: "assistant-a",
        role: "assistant",
        text: "准备创建节点",
        displayName: "Agent",
        timestamp: Date.now(),
        turnId: "turn-a",
        attachments: [],
      },
    ];

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    act(() => {
      window.dispatchEvent(new CustomEvent("freezone/canvas-context-activity", {
        detail: {
          type: "canvas.context.activity",
          turn_id: "turn-a",
          bridge_key: "validation-a",
          canvas_id: "canvas-a",
          status: "done",
          labels: ["命令校验"],
          errors: [],
          received_at: 1,
          surface_order: 1,
        },
      }));
      window.dispatchEvent(new CustomEvent("freezone/canvas-command-approval", {
        detail: {
          canvasId: "canvas-a",
          turnId: "turn-a",
          bridgeKey: "bridge-a",
          envelopes: [
            {
              schema_version: "canvas_chat_commands.v1",
              commands: [
                {
                  type: "create_node",
                  node_type: "imageGenNode",
                  data: { prompt: "test image" },
                },
              ],
            },
          ],
          receivedAt: Date.now(),
        },
      }));
    });

    expect(screen.getByText("待确认的画布操作")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认执行" }));

    await waitFor(() =>
      expect(apiMocks.post).toHaveBeenCalledWith("api/v1/chat/canvas-command-tool-result", expect.objectContaining({
        json: expect.objectContaining({
          bridge_key: "bridge-a",
          turn_id: "turn-a",
          canvas_id: "canvas-a",
          canvas_apply_status: "applied",
        }),
      })),
    );
    expect(apiMocks.post).toHaveBeenCalledWith("api/v1/chat/ui-events", expect.objectContaining({
      json: expect.objectContaining({
        turn_id: "turn-a",
        event: expect.objectContaining({
          type: "canvas_command_result",
          bridge_key: "bridge-a",
        }),
      }),
    }));
  });

  it("does not restore a persisted canvas command approval after it was confirmed", async () => {
    superChatMocks.messages = [
      {
        id: "user-a",
        role: "user",
        text: "加个视频节点",
        displayName: "User",
        timestamp: Date.now(),
        turnId: "turn-a",
        attachments: [],
        raw: {
          ui_events: [
            {
              id: 1,
              type: "canvas_command_approval",
              turn_id: "turn-a",
              schema_version: "canvas_command_approval.v1",
              canvas_id: "canvas-a",
              bridge_key: "bridge-a",
              envelopes: [
                {
                  schema_version: "canvas_chat_commands.v1",
                  canvas_id: "canvas-a",
                  commands: [
                    {
                      type: "create_node",
                      node_type: "videoNode",
                      data: { title: "视频输入" },
                    },
                  ],
                },
              ],
              received_at: 2,
            },
          ],
        },
      } as ChatMessage,
    ];

    const { rerender } = render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    expect(await screen.findByText("待确认的画布操作")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认执行" }));

    await waitFor(() => expect(screen.queryByText("待确认的画布操作")).not.toBeInTheDocument());

    superChatMocks.messages = [
      superChatMocks.messages[0],
      {
        id: "assistant-a",
        role: "assistant",
        text: "已为你添加一个视频节点。",
        displayName: "Agent",
        timestamp: Date.now(),
        turnId: "turn-a",
        attachments: [],
      },
    ] as ChatMessage[];

    rerender(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    await waitFor(() => expect(screen.queryByText("待确认的画布操作")).not.toBeInTheDocument());
    expect(screen.getByText("已为你添加一个视频节点。")).toBeInTheDocument();
  });

  it("shows a canvas command approval even when the agent has no visible message yet", async () => {
    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    act(() => {
      window.dispatchEvent(new CustomEvent("freezone/canvas-context-activity", {
        detail: {
          type: "canvas.context.activity",
          turn_id: "turn-a",
          bridge_key: "validation-a",
          canvas_id: "canvas-a",
          status: "done",
          labels: ["命令校验"],
          errors: [],
          received_at: 1,
          surface_order: 1,
        },
      }));
      window.dispatchEvent(new CustomEvent("freezone/canvas-command-approval", {
        detail: {
          canvasId: "canvas-a",
          turnId: "turn-a",
          bridgeKey: "bridge-a",
          envelopes: [
            {
              schema_version: "canvas_chat_commands.v1",
              commands: [
                {
                  type: "create_node",
                  node_type: "videoNode",
                  data: {},
                },
              ],
            },
          ],
          receivedAt: 1,
        },
      }));
    });

    expect(await screen.findByText("已校验画布命令")).toBeInTheDocument();
    expect(await screen.findByText("待确认的画布操作")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认执行" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认执行" }));
    await waitFor(() => expect(screen.queryByText("待确认的画布操作")).not.toBeInTheDocument());
    expect(await screen.findByText("画布执行")).toBeInTheDocument();
  });

  it("restores a persisted canvas command approval when no assistant message exists yet", async () => {
    superChatMocks.messages = [
      {
        id: "user-a",
        role: "user",
        text: "加个视频节点",
        displayName: "User",
        timestamp: Date.now(),
        turnId: "turn-a",
        attachments: [],
        raw: {
          ui_events: [
            {
              id: 1,
              type: "canvas_command_approval",
              turn_id: "turn-a",
              schema_version: "canvas_command_approval.v1",
              canvas_id: "canvas-a",
              bridge_key: "bridge-a",
              envelopes: [
                {
                  schema_version: "canvas_chat_commands.v1",
                  canvas_id: "canvas-a",
                  commands: [
                    {
                      type: "create_node",
                      node_type: "videoNode",
                      data: { title: "视频输入" },
                    },
                  ],
                },
              ],
              received_at: 2,
            },
          ],
        },
      } as ChatMessage,
    ];

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    expect(await screen.findByText("待确认的画布操作")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认执行" })).toBeInTheDocument();
  });

  it("does not restore a persisted canvas command approval when a result already exists", async () => {
    superChatMocks.messages = [
      {
        id: "user-a",
        role: "user",
        text: "加个视频节点",
        displayName: "User",
        timestamp: Date.now(),
        turnId: "turn-a",
        attachments: [],
        raw: {
          ui_events: [
            {
              id: 1,
              type: "canvas_command_approval",
              turn_id: "turn-a",
              schema_version: "canvas_command_approval.v1",
              canvas_id: "canvas-a",
              bridge_key: "bridge-a",
              envelopes: [
                {
                  schema_version: "canvas_chat_commands.v1",
                  canvas_id: "canvas-a",
                  commands: [
                    {
                      type: "create_node",
                      node_type: "videoNode",
                      data: { title: "视频输入" },
                    },
                  ],
                },
              ],
              received_at: 2,
            },
            {
              id: 2,
              type: "canvas_command_result",
              turn_id: "turn-a",
              schema_version: "canvas_command_result.v1",
              canvas_id: "canvas-a",
              bridge_key: "bridge-a",
              result: {
                applied: 0,
                openedUiActions: 0,
                createdNodeIds: [],
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
              },
              received_at: 3,
              cancelled: true,
            },
          ],
        },
      } as ChatMessage,
    ];

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    await waitFor(() => expect(screen.queryByText("待确认的画布操作")).not.toBeInTheDocument());
  });

  it("reports and persists cancelled canvas command approvals", async () => {
    superChatMocks.messages = [
      {
        id: "assistant-a",
        role: "assistant",
        text: "准备创建节点",
        displayName: "Agent",
        timestamp: Date.now(),
        turnId: "turn-a",
        attachments: [],
      },
    ];

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    act(() => {
      window.dispatchEvent(new CustomEvent("freezone/canvas-command-approval", {
        detail: {
          canvasId: "canvas-a",
          turnId: "turn-a",
          bridgeKey: "bridge-a",
          envelopes: [
            {
              schema_version: "canvas_chat_commands.v1",
              commands: [
                {
                  type: "create_node",
                  node_type: "imageGenNode",
                  data: { prompt: "test image" },
                },
              ],
            },
          ],
          receivedAt: Date.now(),
        },
      }));
    });

    expect(await screen.findByText("待确认的画布操作")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));

    await waitFor(() =>
      expect(apiMocks.post).toHaveBeenCalledWith("api/v1/chat/canvas-command-tool-result", expect.objectContaining({
        json: expect.objectContaining({
          bridge_key: "bridge-a",
          turn_id: "turn-a",
          canvas_apply_status: "cancelled_by_user",
          cancelled: true,
          errors: ["已取消画布操作"],
        }),
      })),
    );
    expect(apiMocks.post).toHaveBeenCalledWith("api/v1/chat/ui-events", expect.objectContaining({
      json: expect.objectContaining({
        turn_id: "turn-a",
        event: expect.objectContaining({
          type: "canvas_command_result",
          bridge_key: "bridge-a",
          cancelled: true,
        }),
      }),
    }));
  });

  it("automatically cancels canvas command approvals after the countdown", async () => {
    superChatMocks.messages = [
      {
        id: "assistant-a",
        role: "assistant",
        text: "准备创建节点",
        displayName: "Agent",
        timestamp: Date.now(),
        turnId: "turn-a",
        attachments: [],
      },
    ];

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    act(() => {
      window.dispatchEvent(new CustomEvent("freezone/canvas-command-approval", {
        detail: {
          canvasId: "canvas-a",
          turnId: "turn-a",
          bridgeKey: "bridge-a",
          envelopes: [
            {
              schema_version: "canvas_chat_commands.v1",
              commands: [
                {
                  type: "create_node",
                  node_type: "imageGenNode",
                  data: { prompt: "test image" },
                },
              ],
            },
          ],
          receivedAt: Date.now() - 31_000,
        },
      }));
    });

    await waitFor(() =>
      expect(apiMocks.post).toHaveBeenCalledWith("api/v1/chat/canvas-command-tool-result", expect.objectContaining({
        json: expect.objectContaining({
          bridge_key: "bridge-a",
          turn_id: "turn-a",
          canvas_apply_status: "cancelled_by_user",
          cancelled: true,
          errors: ["画布操作等待超时，已自动取消"],
        }),
      })),
    );
    expect(apiMocks.post).toHaveBeenCalledWith("api/v1/chat/ui-events", expect.objectContaining({
      json: expect.objectContaining({
        turn_id: "turn-a",
        event: expect.objectContaining({
          type: "canvas_command_result",
          bridge_key: "bridge-a",
          cancelled: true,
          cancel_reason: "timeout",
        }),
      }),
    }));
  });

  it("shows a countdown before canvas approval buttons", async () => {
    superChatMocks.messages = [
      {
        id: "assistant-a",
        role: "assistant",
        text: "准备创建节点",
        displayName: "Agent",
        timestamp: Date.now(),
        turnId: "turn-a",
        attachments: [],
      },
    ];

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    act(() => {
      window.dispatchEvent(new CustomEvent("freezone/canvas-command-approval", {
        detail: {
          canvasId: "canvas-a",
          turnId: "turn-a",
          bridgeKey: "bridge-a",
          envelopes: [
            {
              schema_version: "canvas_chat_commands.v1",
              commands: [
                {
                  type: "create_node",
                  node_type: "imageGenNode",
                  data: { prompt: "test image" },
                },
              ],
            },
          ],
          receivedAt: Date.now(),
        },
      }));
    });

    expect(await screen.findByText("待确认的画布操作")).toBeInTheDocument();
    expect(screen.getByText(/秒后自动取消/)).toBeInTheDocument();
  });

  it("renders Freezone tool calls as activity cards", async () => {
    superChatMocks.showToolEvents = true;
    superChatMocks.messages = [
      {
        id: "tool-a",
        role: "tool",
        text: "freezone_create_node",
        displayName: "Tool",
        timestamp: Date.now(),
        turnId: "turn-a",
        attachments: [],
        raw: {
          type: "tool.call",
          name: "freezone_create_node",
          input: { project_id: "project-a", canvas_id: "canvas-a" },
        },
      } as ChatMessage,
    ];

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    expect(await screen.findByText("创建节点")).toBeInTheDocument();
    expect(screen.getByText("进行中")).toBeInTheDocument();
    expect(screen.getByText("项目：project-a")).toBeInTheDocument();
  });

  it("hides protocol narration when a canvas command approval is shown", async () => {
    superChatMocks.messages = [
      {
        id: "assistant-a",
        role: "assistant",
        text: "canvas_chat_commands.v1\n{\"commands\":[]}",
        displayName: "Agent",
        timestamp: Date.now(),
        turnId: "turn-a",
        attachments: [],
      },
    ];

    render(
      <SuperChatPanel
        variant="freezone"
        canvasId="canvas-a"
        currentCanvasSelection={[]}
        currentCanvasOntologyContext={buildCanvasOntologyContext([], [], {
          canvasId: "canvas-a",
          selectedNodeIds: [],
        })}
        pendingAttachments={[]}
      />,
    );

    act(() => {
      window.dispatchEvent(new CustomEvent("freezone/canvas-command-approval", {
        detail: {
          canvasId: "canvas-a",
          turnId: "turn-a",
          bridgeKey: "bridge-a",
          envelopes: [
            {
              schema_version: "canvas_chat_commands.v1",
              commands: [
                {
                  type: "create_node",
                  node_type: "imageGenNode",
                  data: { prompt: "test image" },
                },
              ],
            },
          ],
          receivedAt: Date.now(),
        },
      }));
    });

    expect(await screen.findByText("待确认的画布操作")).toBeInTheDocument();
    expect(screen.queryByText(/canvas_chat_commands\.v1/)).not.toBeInTheDocument();
  });
});
