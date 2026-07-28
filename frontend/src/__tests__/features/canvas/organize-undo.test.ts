// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useOrganizeUndo } from "@/features/canvas/hooks/useOrganizeUndo";
import { CANVAS_NODE_TYPES } from "@/features/canvas/domain/canvasNodes";
import { useCanvasStore } from "@/stores/canvasStore";

const VIEWPORT = { x: 120, y: -40, zoom: 0.75 };

/** 模拟一次「整理画布」:先写入新坐标,再拍下整理前的快照(顺序和 Canvas.tsx 一致)。 */
function organize(
  capture: (
    positions: Record<string, { x: number; y: number }>,
    viewport: { x: number; y: number; zoom: number },
  ) => void,
  before: Record<string, { x: number; y: number }>,
  after: Record<string, { x: number; y: number }>,
) {
  useCanvasStore.getState().setNodePositions(after);
  capture(before, VIEWPORT);
}

describe("useOrganizeUndo — 整理画布的保留 / 还原", () => {
  let nodeId = "";

  beforeEach(() => {
    useCanvasStore.getState().setCanvasData([], []);
    nodeId = useCanvasStore
      .getState()
      .addNode(CANVAS_NODE_TYPES.upload, { x: 10, y: 20 }, {});
  });

  it("整理之后挂起快照,并且不会被整理自己那一次编辑立刻清掉", () => {
    const { result } = renderHook(() => useOrganizeUndo());

    act(() => {
      organize(result.current.capture, { [nodeId]: { x: 10, y: 20 } }, { [nodeId]: { x: 400, y: 300 } });
    });

    expect(result.current.pending).not.toBeNull();
    expect(result.current.pending?.viewport).toEqual(VIEWPORT);
    expect(result.current.pending?.positions).toEqual({ [nodeId]: { x: 10, y: 20 } });
  });

  it("「保留」丢掉快照,节点留在整理后的位置", () => {
    const { result } = renderHook(() => useOrganizeUndo());

    act(() => {
      organize(result.current.capture, { [nodeId]: { x: 10, y: 20 } }, { [nodeId]: { x: 400, y: 300 } });
    });
    act(() => {
      result.current.keep();
    });

    expect(result.current.pending).toBeNull();
    expect(useCanvasStore.getState().nodes[0]?.position).toEqual({ x: 400, y: 300 });
  });

  it("「还原」交出整理前的坐标和视口,同一次事件里就能读到(不用等 setState)", () => {
    const { result } = renderHook(() => useOrganizeUndo());

    act(() => {
      organize(result.current.capture, { [nodeId]: { x: 10, y: 20 } }, { [nodeId]: { x: 400, y: 300 } });
    });

    let snapshot: ReturnType<typeof result.current.consume> = null;
    act(() => {
      snapshot = result.current.consume();
      if (snapshot) {
        useCanvasStore.getState().setNodePositions(snapshot.positions);
      }
    });

    expect(snapshot).not.toBeNull();
    expect(snapshot!.viewport).toEqual(VIEWPORT);
    expect(useCanvasStore.getState().nodes[0]?.position).toEqual({ x: 10, y: 20 });
    expect(result.current.pending).toBeNull();
  });

  it("再点一次「还原」不会重放旧快照", () => {
    const { result } = renderHook(() => useOrganizeUndo());

    act(() => {
      organize(result.current.capture, { [nodeId]: { x: 10, y: 20 } }, { [nodeId]: { x: 400, y: 300 } });
    });
    act(() => {
      result.current.consume();
    });

    let second: ReturnType<typeof result.current.consume> = null;
    act(() => {
      second = result.current.consume();
    });
    expect(second).toBeNull();
  });

  // 这条是这个 hook 存在的理由:快照过期后还原会把用户后来的改动一起抹掉。
  it("用户在整理之后又改了画布,快照立刻作废(宁可少给一次后悔机会)", () => {
    const { result } = renderHook(() => useOrganizeUndo());

    act(() => {
      organize(result.current.capture, { [nodeId]: { x: 10, y: 20 } }, { [nodeId]: { x: 400, y: 300 } });
    });
    expect(result.current.pending).not.toBeNull();

    act(() => {
      // 用户手动把节点拖到别处。
      useCanvasStore.getState().setNodePositions({ [nodeId]: { x: 800, y: 800 } });
    });

    expect(result.current.pending).toBeNull();
    expect(result.current.consume()).toBeNull();
  });

  it("整理时没有任何节点移动过就不该有快照(调用方不 capture)", () => {
    const { result } = renderHook(() => useOrganizeUndo());
    expect(result.current.pending).toBeNull();
  });
});
