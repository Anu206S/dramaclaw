import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const readNodeSource = (name: string) =>
  readFileSync(
    resolve(process.cwd(), `src/features/canvas/nodes/${name}.tsx`),
    "utf8",
  );

describe("dynamic workflow node action contract", () => {
  it.each([
    ["TextAnnotationNode", "generate_text"],
    ["ImageGenNode", "generate_image"],
    ["VideoNode", "generate_video"],
    ["AudioNode", "generate_audio"],
    ["VideoComposeNode", "auto_compose_video"],
  ])("keeps %s subscribed to %s", (nodeName, action) => {
    const source = readNodeSource(nodeName);

    expect(source).toContain("subscribeNodeAction");
    expect(source).toContain(action);
    expect(source).toContain("publishNodeActionAccepted");
    expect(source).toContain("publishNodeActionSuccess");
    expect(source).toContain("publishNodeActionError");
  });

  it("keeps offscreen workflow nodes mounted while a run is active", () => {
    const source = readFileSync(
      resolve(process.cwd(), "src/features/canvas/Canvas.tsx"),
      "utf8",
    );

    expect(source).toContain("WORKFLOW_RUN_UPDATED_EVENT");
    expect(source).toContain("onlyRenderVisibleElements={!workflowExecutionActive}");
  });

  it("allows long-running media tasks to finish before timing out", () => {
    const source = readFileSync(
      resolve(process.cwd(), "src/features/freezone/canvasChatCommands.ts"),
      "utf8",
    );

    expect(source).toContain("DEFAULT_NODE_ACTION_TIMEOUT_MS = 30 * 60 * 1000");
  });
});
