// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { describe, expect, it } from "vitest";

import {
  filterFreezoneSkillSuggestions,
  getFreezoneSkillSlashQuery,
  insertFreezoneSkillMention,
  moveFreezoneSkillSuggestionIndex,
  toFreezoneSkillSuggestions,
} from "@/features/superchat/freezone-skill-suggestions";

describe("freezone skill slash suggestions", () => {
  it("builds suggestions only from enabled skills with ids", () => {
    const suggestions = toFreezoneSkillSuggestions([
      {
        id: "poster_design",
        name: "海报设计",
        enabled: true,
        category: "visual",
        description: "海报视觉风格",
        triggers: { keywords: ["海报", { keyword: "视觉" }] },
      },
      { id: "disabled_skill", enabled: false, description: "不展示" },
      { enabled: true, description: "没有 id" },
    ]);

    expect(suggestions).toEqual([
      {
        id: "poster_design",
        label: "海报设计",
        category: "visual",
        description: "海报视觉风格",
        keywords: ["海报", "视觉"],
      },
    ]);
  });

  it("opens only for the current slash token and filters by id, category, description, or keywords", () => {
    const suggestions = toFreezoneSkillSuggestions([
      {
        id: "poster_design",
        category: "visual",
        description: "海报视觉风格",
        triggers: { keywords: ["海报"] },
      },
      {
        id: "copy_plan",
        category: "text",
        description: "详情页文案",
        triggers: { keywords: ["文案"] },
      },
    ]);

    expect(getFreezoneSkillSlashQuery("/")).toBe("");
    expect(getFreezoneSkillSlashQuery("请用 /post")).toBe("post");
    expect(getFreezoneSkillSlashQuery("请用 /post 继续")).toBeNull();
    expect(filterFreezoneSkillSuggestions(suggestions, "视觉").map((item) => item.id)).toEqual([
      "poster_design",
    ]);
    expect(filterFreezoneSkillSuggestions(suggestions, "text").map((item) => item.id)).toEqual([
      "copy_plan",
    ]);
  });

  it("inserts the selected skill as visible prompt text without hidden metadata", () => {
    expect(insertFreezoneSkillMention("/", "poster_design")).toBe("/poster_design ");
    expect(insertFreezoneSkillMention("帮我 /post", "poster_design")).toBe("帮我 /poster_design ");
    expect(insertFreezoneSkillMention("第一行\n/post", "poster_design")).toBe("第一行\n/poster_design ");
    expect(insertFreezoneSkillMention("帮我做", "poster_design")).toBe("帮我做 /poster_design ");
  });

  it("cycles the active suggestion index with arrow keys", () => {
    expect(moveFreezoneSkillSuggestionIndex(0, 1, 3)).toBe(1);
    expect(moveFreezoneSkillSuggestionIndex(2, 1, 3)).toBe(0);
    expect(moveFreezoneSkillSuggestionIndex(0, -1, 3)).toBe(2);
    expect(moveFreezoneSkillSuggestionIndex(8, 1, 2)).toBe(1);
    expect(moveFreezoneSkillSuggestionIndex(0, 1, 0)).toBe(0);
  });
});
