// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// 询价与提交禁用条件住在共用 hook 里：工作流的 ImageGenNode 和故事板的
// AssetBoardImageGenForm 都挂它，一处口径两个视图同价。扫宿主只会扫到一个
// spread，扫不到真正的计费逻辑。
const nodeSource = readFileSync(
  "src/features/canvas/nodes/shared/useImageGenerationForm.ts",
  "utf8",
);

describe("canvas image generation credit contract", () => {
  it("quotes the explicit image-generation feature with model details and count", () => {
    expect(nodeSource).toContain(
      "imageSelectionForCost ? IMAGE_GENERATE_FEATURE_KEY : null",
    );
    expect(nodeSource).toContain(
      "params: buildImageFeatureBillingParams(selectedModel",
    );
    expect(nodeSource).toContain("pricing_quantity: imageQuantity");
    expect(nodeSource).toContain("quantity: imageQuantity");
  });

  it("shows and blocks on an unconfigured image-generation rule", () => {
    expect(nodeSource).toContain(
      "imageCreditCost.error instanceof BillingRuleNotConfiguredError",
    );
    expect(nodeSource).toContain("t('common.billingRuleNotConfiguredShort')");
    expect(nodeSource).toContain("const submitDisabled =");
    expect(nodeSource).toContain("imageBillingRuleMissing ||");
    expect(nodeSource).toContain("图片生成未启动");
    expect(nodeSource).toContain(
      "generationError: billingRuleMissingSubmitMessage",
    );
  });
});
