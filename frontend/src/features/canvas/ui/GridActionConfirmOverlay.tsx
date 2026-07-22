// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { memo, useCallback } from 'react';
import { NodeToolbar as ReactFlowNodeToolbar, Position } from '@xyflow/react';
import { ArrowUp, Image as ImageIcon, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { type CanvasNode } from '@/features/canvas/domain/canvasNodes';
import {
  submitGridTemplateAction,
  type GridActionKey,
} from '@/features/canvas/application/gridTemplateAction';
import { CreditCostInline } from '@/components/credit-cost-inline';
import { useFreezoneImageModels } from '@/features/canvas/hooks/useFreezoneImageModels';
import { useGenerationCreditCost } from '@/lib/queries/generation-credit-cost';
import { NODE_TOOLBAR_CLASS } from './nodeToolbarConfig';
import { CANVAS_NODE_TOOLBAR_PILL_CLASS } from './nodeFrameStyles';

// 提交编排移到 application/gridTemplateAction（故事板详情工具条共用）；key 类型
// 原地 re-export，NodeActionToolbar 等既有引用无需改动。
export type { GridActionKey } from '@/features/canvas/application/gridTemplateAction';

/** 是否该图片模型支持 quality 参数（宫格活价查询需要按模型带上正确的 params）。 */
export function imageModelSupportsQuality(apiModel: string | null | undefined): boolean {
  const normalized = String(apiModel ?? '').trim().toLowerCase();
  return (
    normalized === 'gpt-image-2'
    || normalized === 'image-2'
    || normalized === 'image-2-official'
    || normalized.includes('gpt-image')
  );
}

export interface GridActionRequest {
  nodeId: string;
  key: GridActionKey;
  label: string;
  prompt: string;
  cost: number;
}

export interface GridActionSubmitPayload {
  sourceNodeId: string;
  imageSource: string;
  actionKey: GridActionKey;
  label: string;
  prompt: string;
  cost: number;
  generationMode: 'image_reference';
  requestAspectRatio: 'auto';
  submittedAt: string;
}

interface GridActionConfirmOverlayProps {
  node: CanvasNode;
  imageSource: string;
  request: GridActionRequest;
  onClose: () => void;
}

export const GridActionConfirmOverlay = memo(
  ({ node, imageSource, request, onClose }: GridActionConfirmOverlayProps) => {
    const { t } = useTranslation();
    const { models: imageModels } = useFreezoneImageModels();
    const selectedModel = imageModels[0];
    const gridActionCost = useGenerationCreditCost(
      'image_selection',
      selectedModel?.apiModel ?? null,
      {
        surface: 'canvas',
        params: imageModelSupportsQuality(selectedModel?.apiModel)
          ? { size: '2K', quality: 'medium' }
          : { size: '2K' },
      },
    );

    // 结果节点创建 + 提交编排在 submitGridTemplateAction（首个 await 之前同步建节点，
    // 因此这里紧跟着的 onClose 与旧内联实现时序一致）。
    const handleSubmit = useCallback(() => {
      void submitGridTemplateAction({
        sourceNodeId: node.id,
        imageSource,
        key: request.key,
        label: request.label,
      });
      onClose();
    }, [imageSource, node.id, onClose, request.key, request.label]);

    return (
      <ReactFlowNodeToolbar
        nodeId={node.id}
        isVisible
        position={Position.Bottom}
        align="center"
        offset={12}
        className={NODE_TOOLBAR_CLASS}
      >
        <div
          className={`flex min-w-[420px] items-center gap-2 ${CANVAS_NODE_TOOLBAR_PILL_CLASS}`}
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-bg-dark/70 text-text-muted transition-colors hover:bg-bg-dark hover:text-text-dark"
            onClick={onClose}
            title={t('nodeToolbar.gridMenu.confirmBar.close')}
          >
            <X className="h-4 w-4" />
          </button>

          <div className="flex min-w-0 flex-1 items-center gap-1.5 px-2 text-xs text-text-dark">
            <ImageIcon className="h-3.5 w-3.5 shrink-0 text-text-muted" />
            <span className="truncate font-medium">{request.label}</span>
          </div>
          <CreditCostInline display={gridActionCost.data?.data.display} />

          <button
            type="button"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-bg-dark transition-colors hover:bg-white/90"
            onClick={handleSubmit}
            title={t('nodeToolbar.gridMenu.confirmBar.submit')}
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        </div>
      </ReactFlowNodeToolbar>
    );
  }
);

GridActionConfirmOverlay.displayName = 'GridActionConfirmOverlay';
