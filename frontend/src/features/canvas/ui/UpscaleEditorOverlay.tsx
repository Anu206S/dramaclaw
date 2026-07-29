// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { memo, useCallback } from 'react';
import { NodeToolbar as ReactFlowNodeToolbar, Position } from '@xyflow/react';

import { type CanvasNode } from '@/features/canvas/domain/canvasNodes';
import { useCanvasStore } from '@/stores/canvasStore';
import { NODE_TOOLBAR_CLASS } from './nodeToolbarConfig';
import { CANVAS_NODE_TOOLBAR_CARD_CLASS } from './nodeFrameStyles';
import { UpscaleEditorPanel, useUpscaleEditor } from './upscaleEditorContent';
import { ZoomScaledToolbar } from './ZoomScaledToolbar';

interface UpscaleEditorOverlayProps {
  /**
   * The upscale-result ExportImage node. The panel is always anchored beneath it
   * while the node is selected — settings are persisted on `node.data` so they
   * survive re-selection.
   */
  node: CanvasNode;
}

/**
 * 工作流画布上的高清放大编辑器外壳：配置卡片挂在节点下方的 NodeToolbar 上，随画布
 * 缩放同步缩放。状态机与卡片本体在 `upscaleEditorContent`，与故事板详情页的
 * `AssetBoardUpscaleForm` 共用。
 */
export const UpscaleEditorOverlay = memo(({ node }: UpscaleEditorOverlayProps) => {
  const deleteNode = useCanvasStore((state) => state.deleteNode);
  const setSelectedNode = useCanvasStore((state) => state.setSelectedNode);

  // 取消 = 放弃这次高清：占位节点本身就是进入编辑器时凭空建出来的，留着只会是个
  // 永远没有产物的空节点。
  const handleCancel = useCallback(() => {
    deleteNode(node.id);
    setSelectedNode(null);
  }, [deleteNode, node.id, setSelectedNode]);

  const controller = useUpscaleEditor({ node, onCancel: handleCancel });

  return (
    <ReactFlowNodeToolbar
      nodeId={node.id}
      isVisible
      position={Position.Bottom}
      align="center"
      offset={12}
      className={NODE_TOOLBAR_CLASS}
    >
      {/* 操作区按画布缩放同步缩放：面板挂在节点下方，锚点取顶边（贴着节点底边），
          画布缩小时面板朝节点收缩、视觉上与节点同比变小。 */}
      <ZoomScaledToolbar origin="top center">
        <UpscaleEditorPanel
          controller={controller}
          className={`w-[400px] p-4 ${CANVAS_NODE_TOOLBAR_CARD_CLASS}`}
        />
      </ZoomScaledToolbar>
    </ReactFlowNodeToolbar>
  );
});

UpscaleEditorOverlay.displayName = 'UpscaleEditorOverlay';
