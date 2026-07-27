import { describe, expect, it } from "vitest";

import {
  assetAnchorSetId,
  buildAssetAnchorPayload,
} from "@/features/canvas/ui/AssetAnchorDialog";

describe("asset anchor dialog payload", () => {
  it("creates a stable canvas-scoped anchor id", () => {
    expect(assetAnchorSetId("canvas_story_01", "8F6A-Node")).toBe(
      "anchor-canvas_story_01-8f6a-node",
    );
  });

  it("builds an enabled anchor without manual node id input", () => {
    expect(buildAssetAnchorPayload({
      canvasId: "canvas-a",
      label: "黑色运动相机",
      name: "运动相机商品锚点",
      nodeId: "node-123",
      nodeType: "imageGenNode",
      projectId: "project-a",
      role: "product",
    })).toMatchObject({
      id: "anchor-canvas-a-node-123",
      enabled: true,
      name: "运动相机商品锚点",
      project_id: "project-a",
      canvas_id: "canvas-a",
      anchors: [
        {
          node_id: "node-123",
          node_type: "imageGenNode",
          label: "黑色运动相机",
          target_item_ids: [],
        },
      ],
    });
  });
});
