// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CanvasZoomControl } from "@/features/canvas/ui/CanvasZoomControl";

const translations: Record<string, string> = {
  "canvas.toolbar.organize": "整理 / 定位画布",
  "canvas.toolbar.organizeShortcut": "⌥⇧F",
  "canvas.toolbar.organizeConfirm": "是否保留此次整理结果？",
  "canvas.toolbar.organizeKeep": "保留",
  "canvas.toolbar.organizeRevert": "还原",
  "canvas.toolbar.hideEdges": "隐藏连线",
  "canvas.toolbar.showEdges": "显示连线",
  "canvas.zoom.menuLabel": "缩放",
  "canvas.zoom.inputLabel": "缩放比例",
  "canvas.zoom.zoomIn": "放大",
  "canvas.zoom.zoomOut": "缩小",
  "canvas.zoom.fitView": "适应视图",
};

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      (translations[key] ?? key).replace(
        /\{\{(\w+)\}\}/g,
        (_match, name: string) => String(options?.[name] ?? ""),
      ),
  }),
}));

vi.mock("@xyflow/react", () => ({
  useReactFlow: () => ({ zoomTo: vi.fn(), getZoom: () => 1, fitView: vi.fn() }),
  useViewport: () => ({ x: 0, y: 0, zoom: 1 }),
}));

function renderControl(props: Partial<Parameters<typeof CanvasZoomControl>[0]> = {}) {
  const onKeepOrganize = vi.fn();
  const onRevertOrganize = vi.fn();
  render(
    <CanvasZoomControl
      onOrganize={vi.fn()}
      onKeepOrganize={onKeepOrganize}
      onRevertOrganize={onRevertOrganize}
      {...props}
    />,
  );
  return { onKeepOrganize, onRevertOrganize };
}

describe("CanvasZoomControl — 整理画布的保留 / 还原确认条", () => {
  it("平时不显示确认条", () => {
    renderControl();
    expect(screen.queryByText("是否保留此次整理结果？")).not.toBeInTheDocument();
  });

  it("整理之后浮出确认条,两个按钮分别接到保留 / 还原", async () => {
    const user = userEvent.setup();
    const { onKeepOrganize, onRevertOrganize } = renderControl({ organizeConfirmOpen: true });

    expect(screen.getByText("是否保留此次整理结果？")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "还原" }));
    expect(onRevertOrganize).toHaveBeenCalledTimes(1);
    expect(onKeepOrganize).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "保留" }));
    expect(onKeepOrganize).toHaveBeenCalledTimes(1);
  });

  // 确认条和缩放菜单抢同一个锚点。让位可以,但不能因此把这次整理默认判成「保留」。
  it("缩放菜单展开时确认条让位,收起菜单后原样回来", async () => {
    const user = userEvent.setup();
    const { onKeepOrganize } = renderControl({ organizeConfirmOpen: true });

    const zoomButton = screen.getByRole("button", { name: "缩放" });
    await user.click(zoomButton);
    expect(screen.queryByText("是否保留此次整理结果？")).not.toBeInTheDocument();

    await user.click(zoomButton);
    expect(screen.getByText("是否保留此次整理结果？")).toBeInTheDocument();
    expect(onKeepOrganize).not.toHaveBeenCalled();
  });
});
