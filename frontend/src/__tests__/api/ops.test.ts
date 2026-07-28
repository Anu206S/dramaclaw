// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiCall } from "@/api/client";
import {
  compileFreezoneRecipePrompt,
  generateFreezoneRecipeText,
} from "@/api/ops";

vi.mock("@/api/client", () => ({
  apiCall: vi.fn(),
  apiClient: vi.fn(),
}));

describe("freezone recipe API", () => {
  beforeEach(() => {
    vi.mocked(apiCall).mockReset();
  });

  it("allows long-running text generation requests", async () => {
    vi.mocked(apiCall).mockResolvedValueOnce({ content: "创意大纲" });

    const content = await generateFreezoneRecipeText({
      recipeId: "video-creative-outline",
      nodePrompt: "生成广告创意大纲",
      userGoal: "制作运动相机广告",
    });

    expect(content).toBe("创意大纲");
    expect(apiCall).toHaveBeenCalledWith(
      "freezone/recipes/generate-text",
      expect.objectContaining({
        method: "POST",
        timeout: 10 * 60 * 1000,
      }),
    );
  });

  it("allows long-running prompt compilation before media submission", async () => {
    vi.mocked(apiCall).mockResolvedValueOnce({ prompt: "编译后的图片提示词" });

    const prompt = await compileFreezoneRecipePrompt({
      recipeId: "video-storyboard-grid",
      recipeVersion: "3.0.0",
      recipePipeline: [{ id: "cinematic-lighting", version: "2.0.0" }],
      skillId: "video-ad",
      skillVersion: "2.0.0",
      confirmedInputs: { aspect_ratio: "9:16" },
      nodeKind: "image",
      nodePrompt: "生成多宫格分镜图",
      userGoal: "制作运动相机广告",
    });

    expect(prompt).toBe("编译后的图片提示词");
    expect(apiCall).toHaveBeenCalledWith(
      "freezone/recipes/compile",
      expect.objectContaining({
        method: "POST",
        timeout: 10 * 60 * 1000,
        json: expect.objectContaining({
          recipe_version: "3.0.0",
          recipe_pipeline: [{ id: "cinematic-lighting", version: "2.0.0" }],
          skill_id: "video-ad",
          skill_version: "2.0.0",
          confirmed_inputs: { aspect_ratio: "9:16" },
        }),
      }),
    );
  });
});
