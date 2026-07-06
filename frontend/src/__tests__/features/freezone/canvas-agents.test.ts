// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { beforeEach, describe, expect, it } from "vitest";

import {
  addFreezoneCanvasAgent,
  DEFAULT_FREEZONE_AGENT_ID,
  loadFreezoneCanvasAgents,
  selectFreezoneCanvasAgent,
  shouldConnectFreezoneCanvasAgent,
  updateFreezoneCanvasAgentFromUserMessage,
} from "@/features/freezone/canvasAgents";

describe("Freezone canvas agents", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("creates a default main agent for a canvas", () => {
    const state = loadFreezoneCanvasAgents("project-a", "canvas-a", 1000);

    expect(state.activeAgentId).toBe(DEFAULT_FREEZONE_AGENT_ID);
    expect(state.agents).toEqual([
      {
        id: DEFAULT_FREEZONE_AGENT_ID,
        name: "新对话",
        createdAt: 1000,
        lastActiveAt: 1000,
      },
    ]);
  });

  it("adds new conversations without changing another canvas", () => {
    const first = addFreezoneCanvasAgent("project-a", "canvas-a", 2000);
    const second = addFreezoneCanvasAgent("project-a", "canvas-a", 3000);
    const otherCanvas = loadFreezoneCanvasAgents("project-a", "canvas-b", 4000);

    expect(first.agent).toMatchObject({ id: "agent-2", name: "新对话" });
    expect(second.agent).toMatchObject({ id: "agent-3", name: "新对话" });
    expect(second.state.activeAgentId).toBe("agent-3");
    expect(second.state.agents.map((agent) => agent.id)).toEqual([
      "main",
      "agent-2",
      "agent-3",
    ]);
    expect(otherCanvas.agents.map((agent) => agent.id)).toEqual(["main"]);
  });

  it("persists the active agent per canvas without reordering recency", () => {
    loadFreezoneCanvasAgents("project-a", "canvas-a", 1000);
    addFreezoneCanvasAgent("project-a", "canvas-a", 2000);
    const selected = selectFreezoneCanvasAgent("project-a", "canvas-a", "main");

    expect(selected.activeAgentId).toBe("main");
    expect(selected.agents.find((agent) => agent.id === "main")?.lastActiveAt).toBe(1000);
    expect(loadFreezoneCanvasAgents("project-a", "canvas-a", 4000).activeAgentId).toBe("main");
  });

  it("titles a conversation from its first user message only", () => {
    loadFreezoneCanvasAgents("project-a", "canvas-a", 1000);

    const titled = updateFreezoneCanvasAgentFromUserMessage(
      "project-a",
      "canvas-a",
      "main",
      "我想做个广告短片",
      2000,
    );
    const afterFollowUp = updateFreezoneCanvasAgentFromUserMessage(
      "project-a",
      "canvas-a",
      "main",
      "再加一个音乐节点",
      3000,
    );

    expect(titled.agents.find((agent) => agent.id === "main")).toMatchObject({
      name: "我想做个广告短片",
      lastActiveAt: 2000,
    });
    expect(afterFollowUp.agents.find((agent) => agent.id === "main")).toMatchObject({
      name: "我想做个广告短片",
      lastActiveAt: 3000,
    });
  });

  it("keeps creation timestamps stable when conversations receive new messages", () => {
    loadFreezoneCanvasAgents("project-a", "canvas-a", 1000);
    addFreezoneCanvasAgent("project-a", "canvas-a", 2000);
    addFreezoneCanvasAgent("project-a", "canvas-a", 3000);

    const afterOldConversationMessage = updateFreezoneCanvasAgentFromUserMessage(
      "project-a",
      "canvas-a",
      "main",
      "你好",
      4000,
    );

    expect(afterOldConversationMessage.agents.map((agent) => [agent.id, agent.createdAt])).toEqual([
      ["main", 1000],
      ["agent-2", 2000],
      ["agent-3", 3000],
    ]);
    expect(afterOldConversationMessage.agents.find((agent) => agent.id === "main")?.lastActiveAt).toBe(4000);
  });

  it("keeps websocket connections only for active or busy agents", () => {
    expect(shouldConnectFreezoneCanvasAgent({ active: true, busy: false })).toBe(true);
    expect(shouldConnectFreezoneCanvasAgent({ active: false, busy: true })).toBe(true);
    expect(shouldConnectFreezoneCanvasAgent({ active: false, busy: false })).toBe(false);
  });
});
