// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useCanvasStore } from "@/stores/canvasStore";

/**
 * 「添加到对话」的落地半边：把节点追加进画布选中集合。
 *
 * 引用不另起一套状态——现有的「选中 → canvas_node_reference 附件」管线
 * （FreezoneShell 的 currentCanvasSelectionAttachment）会把它渲染成输入框里的
 * 引用条，移除引用条 = 取消选中（见 superchat-panel 的 deselectFreezoneNodeReferences）。
 *
 * 追加而非替换：连点几个节点应该攒成一组上下文，这也是它区别于直接点节点的地方
 * （点节点走节点根的 onClick，会把选中收成单选）。
 *
 * @returns 是否真的选中了节点（传进来的 id 全都不在画布上时为 false）。
 */
export function selectNodesForChatReference(nodeIds: string[]): boolean {
  const store = useCanvasStore.getState();
  const existingIds = new Set(store.nodes.map((node) => node.id));
  const targetIds = nodeIds.filter((nodeId) => existingIds.has(nodeId));
  if (targetIds.length === 0) return false;
  store.onNodesChange(
    targetIds.map((nodeId) => ({ id: nodeId, type: "select" as const, selected: true })),
  );
  // selectedNodeId 只在单选时有意义（与 superchat 取消引用时的收敛规则一致），
  // 多选状态下留 null，让 visibleSelectedCanvasNodes 走 node.selected 那条路。
  const selectedNodes = useCanvasStore.getState().nodes.filter((node) => node.selected);
  store.setSelectedNode(selectedNodes.length === 1 ? (selectedNodes[0]?.id ?? null) : null);
  return true;
}
