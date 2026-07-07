// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import type { FreezoneAgentConfigPayload } from "@/lib/queries/freezone-agent-config";

export type FreezoneSkillSuggestion = {
  id: string;
  label: string;
  category: string;
  description: string;
  keywords: string[];
};

function readString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function readKeywords(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const keywords: string[] = [];
  for (const item of value) {
    if (typeof item === "string") {
      const keyword = item.trim();
      if (keyword) keywords.push(keyword);
      continue;
    }
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const keyword = readString(record.keyword) || readString(record.text) || readString(record.value);
    if (keyword) keywords.push(keyword);
  }
  return keywords;
}

export function toFreezoneSkillSuggestions(
  items: FreezoneAgentConfigPayload[] | undefined,
): FreezoneSkillSuggestion[] {
  if (!items?.length) return [];
  return items.flatMap((item) => {
    const id = readString(item.id);
    if (!id || item.enabled === false) return [];
    const triggers = item.triggers && typeof item.triggers === "object"
      ? item.triggers as Record<string, unknown>
      : {};
    return [{
      id,
      label:
        readString(item.name)
        || readString(item.display_name)
        || readString(item.displayName)
        || readString(item.title)
        || id,
      category: readString(item.category),
      description: readString(item.description),
      keywords: readKeywords(triggers.keywords),
    }];
  });
}

export function getFreezoneSkillSlashQuery(value: string): string | null {
  const match = value.match(/(?:^|\s)\/([^\s/]*)$/u);
  return match ? match[1].trim().toLowerCase() : null;
}

export function filterFreezoneSkillSuggestions(
  suggestions: FreezoneSkillSuggestion[],
  query: string,
): FreezoneSkillSuggestion[] {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return suggestions;
  return suggestions.filter((suggestion) => {
    const haystack = [
      suggestion.id,
      suggestion.label,
      suggestion.category,
      suggestion.description,
      ...suggestion.keywords,
    ].join("\n").toLowerCase();
    return haystack.includes(normalizedQuery);
  });
}

export function insertFreezoneSkillMention(value: string, skillId: string): string {
  const replacement = `/${skillId} `;
  const slashTokenMatch = value.match(/(?:^|\s)\/([^\s/]*)$/u);
  if (!slashTokenMatch || slashTokenMatch.index === undefined) {
    return `${value}${value && !/\s$/u.test(value) ? " " : ""}${replacement}`;
  }
  const matchedToken = slashTokenMatch[0];
  const tokenStart = slashTokenMatch.index + (matchedToken.startsWith("/") ? 0 : 1);
  return `${value.slice(0, tokenStart)}${replacement}`;
}

export function moveFreezoneSkillSuggestionIndex(
  currentIndex: number,
  offset: number,
  itemCount: number,
): number {
  if (itemCount <= 0) return 0;
  const normalizedCurrent = currentIndex >= 0 && currentIndex < itemCount ? currentIndex : 0;
  return (normalizedCurrent + offset + itemCount) % itemCount;
}
