// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import type { ChatAttachment, ChatMessage, ChatRole } from "@/features/superchat/types";
import { hasStructuredContent } from "@/features/superchat/spec-extract";

const INTERNAL_CONTEXT_BLOCK_RE =
  /\n?\[((?:DRAMACLAW|SUPERTALE)_[A-Z0-9_]+)\][\s\S]*?\[\/\1\]\n?/g;
const EMPTY_AGENT_REPLY_TEXT = "这轮操作没有收到虾导的有效回复，请稍后重试。";
const EMPTY_AGENT_REPLY_PLACEHOLDERS = new Set([
  "(hermes returned no content)",
  "(agent returned no content)",
]);

function stripInternalContextBlocks(text: string): string {
  return text.replace(INTERNAL_CONTEXT_BLOCK_RE, "\n").trim();
}

function normalizeDisplayText(text: string): string {
  const trimmed = text.trim();
  return EMPTY_AGENT_REPLY_PLACEHOLDERS.has(trimmed) ? EMPTY_AGENT_REPLY_TEXT : text;
}

function textFromContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((block) => {
      if (typeof block === "string") return block;
      if (!block || typeof block !== "object") return "";
      const value = block as Record<string, unknown>;
      if (typeof value.text === "string") return value.text;
      if (typeof value.content === "string") return value.content;
      return "";
    })
    .filter(Boolean)
    .join("\n");
}

export function extractMessageText(message: unknown): string {
  if (typeof message === "string") return normalizeDisplayText(stripInternalContextBlocks(message));
  if (!message || typeof message !== "object") return "";
  const value = message as Record<string, unknown>;
  if (typeof value.text === "string") return normalizeDisplayText(stripInternalContextBlocks(value.text));
  if (typeof value.message === "string") return normalizeDisplayText(stripInternalContextBlocks(value.message));
  if (typeof value.content === "string") return normalizeDisplayText(stripInternalContextBlocks(value.content));
  return normalizeDisplayText(stripInternalContextBlocks(textFromContent(value.content)));
}

function normalizeRole(role: unknown): ChatRole {
  if (role === "user") return "user";
  if (role === "system") return "system";
  if (role === "tool" || role === "tool_result" || role === "toolResult" || role === "trace") return "tool";
  return "assistant";
}

function normalizeId(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

function normalizeTimestamp(value: Record<string, unknown>): number {
  if (typeof value.timestamp === "number") return value.timestamp;
  if (typeof value.created_at === "string") {
    const parsed = Date.parse(value.created_at);
    if (Number.isFinite(parsed)) return parsed;
  }
  if (typeof value.createdAt === "string") {
    const parsed = Date.parse(value.createdAt);
    if (Number.isFinite(parsed)) return parsed;
  }
  return Date.now();
}

function normalizeTurnId(value: Record<string, unknown>): string | undefined {
  return normalizeId(value.turn_id) ?? normalizeId(value.turnId) ?? undefined;
}

function normalizeUiEvents(value: Record<string, unknown>): unknown[] | undefined {
  const events = Array.isArray(value.ui_events)
    ? value.ui_events
    : Array.isArray(value.uiEvents)
      ? value.uiEvents
      : undefined;
  return events && events.length > 0 ? events : undefined;
}

function mediaKindToType(kind: unknown): string | undefined {
  if (kind === "image" || kind === "video" || kind === "audio" || kind === "file") {
    return kind;
  }
  return undefined;
}

export function normalizeMessage(message: unknown, fallbackRole: ChatRole = "assistant"): ChatMessage | null {
  const text = extractMessageText(message).trim();
  const value = message && typeof message === "object"
    ? (message as Record<string, unknown>)
    : {};
  const uiEvents = normalizeUiEvents(value);
  if (!text && !hasStructuredContent(message) && !uiEvents) return null;
  const id =
    normalizeId(value.id)
    ?? normalizeId(value.messageId)
    ?? `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const timestamp = normalizeTimestamp(value);
  const role = "role" in value ? normalizeRole(value.role) : fallbackRole;
  const turnId = normalizeTurnId(value);
  const displayName = typeof value.displayName === "string" ? value.displayName : undefined;
  const attachments = extractAttachments(value);
  return { id, role, text, turnId, displayName, attachments, uiEvents, timestamp, raw: message };
}

function extractAttachments(value: Record<string, unknown>): ChatAttachment[] {
  const contentAttachments = Array.isArray(value.content)
    ? value.content
    .filter((block) => block && typeof block === "object")
    .map((block) => block as Record<string, unknown>)
    .filter((block) => block.type === "image" || block.type === "file" || block.type === "audio" || block.type === "document")
    .map((block) => {
      const source = block.source && typeof block.source === "object"
        ? (block.source as Record<string, unknown>)
        : {};
      const mimeType =
        typeof block.mimeType === "string"
          ? block.mimeType
          : typeof source.media_type === "string"
            ? source.media_type
            : undefined;
      const data = typeof source.data === "string" ? source.data : undefined;
      return {
        id: typeof block.id === "string" ? block.id : undefined,
        type: typeof block.type === "string" ? block.type : undefined,
        mimeType,
        fileName: typeof block.fileName === "string" ? block.fileName : undefined,
        content: data,
      };
    })
    : [];

  const mediaAttachments = Array.isArray(value.media)
    ? value.media
        .filter((item) => item && typeof item === "object")
        .map((item) => item as Record<string, unknown>)
        .map((item): ChatAttachment => {
          const url = typeof item.url === "string" ? item.url : undefined;
          const path = typeof item.path === "string" ? item.path : undefined;
          const label = typeof item.label === "string" ? item.label : undefined;
          const kind = mediaKindToType(item.kind) ?? "file";
          return {
            id: `${kind}:${path || url || label || Math.random().toString(36).slice(2, 8)}`,
            type: kind,
            kind,
            fileName: label || path?.split("/").pop() || url?.split("/").pop(),
            content: url,
            url,
            path,
            label,
          };
        })
    : [];

  return [...contentAttachments, ...mediaAttachments];
}

export function buildLocalUserMessage(
  text: string,
  turnId: string,
  displayName?: string,
  attachments?: ChatAttachment[],
): ChatMessage {
  return {
    id: `user-${turnId}`,
    role: "user",
    text,
    turnId,
    displayName,
    attachments,
    timestamp: Date.now(),
  };
}
