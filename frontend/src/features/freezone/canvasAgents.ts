// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
export const DEFAULT_FREEZONE_AGENT_ID = "main";
export const DEFAULT_FREEZONE_AGENT_NAME = "新对话";

export type FreezoneCanvasAgent = {
  id: string;
  name: string;
  createdAt: number;
  lastActiveAt: number;
};

export type FreezoneCanvasAgentState = {
  agents: FreezoneCanvasAgent[];
  activeAgentId: string;
};

export function shouldConnectFreezoneCanvasAgent({
  active,
  busy,
}: {
  active: boolean;
  busy: boolean;
}): boolean {
  return active || busy;
}

const STORAGE_PREFIX = "freezone:canvas-agents:v1:";
const GENERATED_AGENT_NAME_RE = /^(Agent(?: \d+)?|新对话)$/;
const MAX_AGENT_TITLE_LENGTH = 32;

function storageKey(projectId: string, canvasId: string): string {
  return `${STORAGE_PREFIX}${projectId}:${canvasId}`;
}

function defaultAgent(now = Date.now()): FreezoneCanvasAgent {
  return {
    id: DEFAULT_FREEZONE_AGENT_ID,
    name: DEFAULT_FREEZONE_AGENT_NAME,
    createdAt: now,
    lastActiveAt: now,
  };
}

function isGeneratedAgentName(name: string): boolean {
  return GENERATED_AGENT_NAME_RE.test(name.trim());
}

function titleFromUserMessage(text: string): string {
  const compact = text
    .replace(/\s+/g, " ")
    .trim();
  if (!compact) return DEFAULT_FREEZONE_AGENT_NAME;
  return compact.length > MAX_AGENT_TITLE_LENGTH
    ? `${compact.slice(0, MAX_AGENT_TITLE_LENGTH - 1)}…`
    : compact;
}

function normalizeState(value: unknown, now = Date.now()): FreezoneCanvasAgentState {
  const fallback = defaultAgent(now);
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { agents: [fallback], activeAgentId: fallback.id };
  }
  const record = value as Record<string, unknown>;
  const parsedAgents = Array.isArray(record.agents) ? record.agents : [];
  const agents = parsedAgents
    .map((item): FreezoneCanvasAgent | null => {
      if (!item || typeof item !== "object" || Array.isArray(item)) return null;
      const agent = item as Record<string, unknown>;
      const id = typeof agent.id === "string" && agent.id.trim() ? agent.id.trim() : "";
      if (!id) return null;
      const name = typeof agent.name === "string" && agent.name.trim() ? agent.name.trim() : id;
      return {
        id,
        name,
        createdAt: typeof agent.createdAt === "number" ? agent.createdAt : now,
        lastActiveAt: typeof agent.lastActiveAt === "number" ? agent.lastActiveAt : now,
      };
    })
    .filter((agent): agent is FreezoneCanvasAgent => Boolean(agent));
  if (!agents.some((agent) => agent.id === DEFAULT_FREEZONE_AGENT_ID)) {
    agents.unshift(fallback);
  }
  const activeAgentId =
    typeof record.activeAgentId === "string"
    && agents.some((agent) => agent.id === record.activeAgentId)
      ? record.activeAgentId
      : DEFAULT_FREEZONE_AGENT_ID;
  return { agents, activeAgentId };
}

function readState(projectId: string, canvasId: string, now = Date.now()): FreezoneCanvasAgentState {
  try {
    return normalizeState(
      JSON.parse(window.localStorage.getItem(storageKey(projectId, canvasId)) || "null"),
      now,
    );
  } catch {
    return normalizeState(null, now);
  }
}

function writeState(projectId: string, canvasId: string, state: FreezoneCanvasAgentState): void {
  window.localStorage.setItem(storageKey(projectId, canvasId), JSON.stringify(state));
}

export function loadFreezoneCanvasAgents(
  projectId: string,
  canvasId: string,
  now = Date.now(),
): FreezoneCanvasAgentState {
  const state = readState(projectId, canvasId, now);
  writeState(projectId, canvasId, state);
  return state;
}

export function addFreezoneCanvasAgent(
  projectId: string,
  canvasId: string,
  now = Date.now(),
): { state: FreezoneCanvasAgentState; agent: FreezoneCanvasAgent } {
  const state = readState(projectId, canvasId, now);
  let index = state.agents.length + 1;
  let id = `agent-${index}`;
  while (state.agents.some((agent) => agent.id === id)) {
    index += 1;
    id = `agent-${index}`;
  }
  const agent: FreezoneCanvasAgent = {
    id,
    name: DEFAULT_FREEZONE_AGENT_NAME,
    createdAt: now,
    lastActiveAt: now,
  };
  const next = {
    agents: [...state.agents, agent],
    activeAgentId: agent.id,
  };
  writeState(projectId, canvasId, next);
  return { state: next, agent };
}

export function selectFreezoneCanvasAgent(
  projectId: string,
  canvasId: string,
  agentId: string,
): FreezoneCanvasAgentState {
  const state = readState(projectId, canvasId);
  const activeAgentId = state.agents.some((agent) => agent.id === agentId)
    ? agentId
    : DEFAULT_FREEZONE_AGENT_ID;
  const next = {
    agents: state.agents,
    activeAgentId,
  };
  writeState(projectId, canvasId, next);
  return next;
}

export function updateFreezoneCanvasAgentFromUserMessage(
  projectId: string,
  canvasId: string,
  agentId: string,
  message: string,
  now = Date.now(),
): FreezoneCanvasAgentState {
  const state = readState(projectId, canvasId, now);
  const normalizedAgentId = state.agents.some((agent) => agent.id === agentId)
    ? agentId
    : DEFAULT_FREEZONE_AGENT_ID;
  const title = titleFromUserMessage(message);
  const next = {
    agents: state.agents.map((agent) => {
      if (agent.id !== normalizedAgentId) return agent;
      return {
        ...agent,
        name: isGeneratedAgentName(agent.name) ? title : agent.name,
        lastActiveAt: now,
      };
    }),
    activeAgentId: state.activeAgentId,
  };
  writeState(projectId, canvasId, next);
  return next;
}
