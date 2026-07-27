// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { beforeEach, describe, expect, it } from "vitest";

import { useCanvasStore } from "@/stores/canvasStore";
import { CANVAS_NODE_TYPES } from "@/features/canvas/domain/canvasNodes";

/**
 * 分组工具条「排列」三档。核心回归点：「宫格排列」必须与多选工具条
 * （MultiSelectionToolbar.handleArrange 的 'graph' 档）走同一套 computeAutoLayout
 * ——有连线就沿边方向左→右分层，而不是旧的 ceil(sqrt(n)) 等宽格子。两个工具条上
 * 同名的菜单项以前会给出不同结果。
 */
describe("arrangeGroupChildren", () => {
  const SIDE_PAD = 20;
  const TOP_PAD = 34;

  beforeEach(() => {
    useCanvasStore.getState().setCanvasData([], []);
  });

  function makeGroup(edges: Array<[string, string]> = []): string {
    // 四个同尺寸节点，初始摆成 2×2，好让「有没有按连线重排」一眼可辨。
    useCanvasStore.getState().setCanvasData(
      [
        { id: "a", position: { x: 0, y: 0 } },
        { id: "b", position: { x: 400, y: 0 } },
        { id: "c", position: { x: 0, y: 300 } },
        { id: "d", position: { x: 400, y: 300 } },
      ].map((n) => ({
        ...n,
        type: CANVAS_NODE_TYPES.imageEdit,
        width: 200,
        height: 150,
        style: { width: 200, height: 150 },
        data: { imageUrl: `${n.id}.png` },
      })),
      edges.map(([source, target]) => ({
        id: `${source}-${target}`,
        source,
        target,
      })),
    );
    const groupId = useCanvasStore.getState().groupNodes(["a", "b", "c", "d"]);
    expect(groupId).not.toBeNull();
    return groupId as string;
  }

  function posOf(id: string): { x: number; y: number } {
    return useCanvasStore.getState().nodes.find((n) => n.id === id)!.position;
  }

  it("宫格排列：有连线时按连线左→右分层，而不是 2×2 方阵", () => {
    // a→b→c→d 一条链：分层布局应把四个节点摊成一排（四层），x 严格递增、
    // 全部同一层高。旧的 ceil(sqrt(4))=2 列实现会摆成 2×2，c/d 换行。
    const groupId = makeGroup([
      ["a", "b"],
      ["b", "c"],
      ["c", "d"],
    ]);
    useCanvasStore.getState().arrangeGroupChildren(groupId, "grid");

    const [a, b, c, d] = ["a", "b", "c", "d"].map(posOf);
    expect(a.x).toBeLessThan(b.x);
    expect(b.x).toBeLessThan(c.x);
    expect(c.x).toBeLessThan(d.x);
    // 链上节点按重心对齐到同一行——这是分层布局的特征，方阵实现给不出。
    expect(new Set([a.y, b.y, c.y, d.y]).size).toBe(1);
  });

  it("宫格排列：结果锚在组内边距上，与 horizontal/vertical 起点一致", () => {
    const groupId = makeGroup([
      ["a", "b"],
      ["b", "c"],
      ["c", "d"],
    ]);
    useCanvasStore.getState().arrangeGroupChildren(groupId, "grid");

    const all = ["a", "b", "c", "d"].map(posOf);
    expect(Math.min(...all.map((p) => p.x))).toBe(SIDE_PAD);
    expect(Math.min(...all.map((p) => p.y))).toBe(TOP_PAD);
  });

  it("水平排列：单行，起点为组内边距", () => {
    const groupId = makeGroup();
    useCanvasStore.getState().arrangeGroupChildren(groupId, "horizontal");

    const all = ["a", "b", "c", "d"].map(posOf);
    expect(new Set(all.map((p) => p.y)).size).toBe(1);
    expect(all[0]).toEqual({ x: SIDE_PAD, y: TOP_PAD });
    // 节点宽 200 + GAP 32
    expect(all[1].x - all[0].x).toBe(232);
  });

  it("垂直排列：单列，起点为组内边距", () => {
    const groupId = makeGroup();
    useCanvasStore.getState().arrangeGroupChildren(groupId, "vertical");

    const all = ["a", "b", "c", "d"].map(posOf);
    expect(new Set(all.map((p) => p.x)).size).toBe(1);
    expect(all[0]).toEqual({ x: SIDE_PAD, y: TOP_PAD });
    // 节点高 150 + GAP 32
    expect(all[1].y - all[0].y).toBe(182);
  });

  it("排列后组框收紧到刚好包住子节点", () => {
    const groupId = makeGroup();
    useCanvasStore.getState().arrangeGroupChildren(groupId, "vertical");

    const g = useCanvasStore.getState().nodes.find((n) => n.id === groupId)!;
    // 单列：宽 = 边距 + 200 + 边距；高 = 顶距 + 4*150 + 3*32 + 边距
    expect(g.style?.width).toBe(SIDE_PAD * 2 + 200);
    expect(g.style?.height).toBe(TOP_PAD + 150 * 4 + 32 * 3 + SIDE_PAD);
  });
});
