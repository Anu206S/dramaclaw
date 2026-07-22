// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { NodeToolbar as ReactFlowNodeToolbar, Position } from '@xyflow/react';
import { ArrowUp, ChevronDown, Globe2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { type CanvasNode } from '@/features/canvas/domain/canvasNodes';
import { CreditCostInline } from '@/components/credit-cost-inline';
import { useCanvasStore } from '@/stores/canvasStore';
import { useGenerationCreditCost } from '@/lib/queries/generation-credit-cost';
import { useFreezoneImageModels } from '@/features/canvas/hooks/useFreezoneImageModels';
import {
  FREEZONE_SCENE_360_ASPECT_RATIOS,
  DEFAULT_FREEZONE_SCENE_360_ASPECT_RATIO,
  type FreezoneScene360AspectRatio,
} from '@/api/ops';
import { scene360Image } from '@/features/canvas/application/imageScene360';
import { NODE_TOOLBAR_CLASS } from './nodeToolbarConfig';
import { CANVAS_NODE_TOOLBAR_PILL_CLASS } from './nodeFrameStyles';
import { ZoomScaledToolbar } from './ZoomScaledToolbar';
import {
  NODE_FLOATING_PANEL_SURFACE_CLASS,
  NODE_GENERATE_BUTTON_BASE_CLASS,
  NODE_GENERATE_BUTTON_ENABLED_CLASS,
} from './nodeControlStyles';

interface Scene360OverlayProps {
  node: CanvasNode;
  imageSource: string;
  onClose: () => void;
}

export const Scene360Overlay = memo(
  ({ node, imageSource, onClose }: Scene360OverlayProps) => {
    const { t } = useTranslation();
    const setSelectedNode = useCanvasStore((state) => state.setSelectedNode);
    const { models: imageModels } = useFreezoneImageModels();
    const selectedModel = imageModels[0];
    const panoCost = useGenerationCreditCost(
      'image_selection',
      selectedModel?.apiModel ?? null,
      {
        surface: 'canvas',
        params: { size: '2K', quality: 'medium' },
      },
    );

    // 全景输出比例（生成参数，仅影响本次出图，不改节点的展示比例）。
    const [aspectRatio, setAspectRatio] = useState<FreezoneScene360AspectRatio>(
      DEFAULT_FREEZONE_SCENE_360_ASPECT_RATIO,
    );

    const handleSubmit = useCallback(() => {
      const result = scene360Image(node.id, imageSource, {
        displayName: t('scene360.label'),
        aspectRatio,
      });
      if (!result) return;
      setSelectedNode(result.nodeId);
      onClose();
    }, [aspectRatio, imageSource, node.id, onClose, setSelectedNode, t]);

    return (
      <ReactFlowNodeToolbar
        nodeId={node.id}
        isVisible
        position={Position.Bottom}
        align="center"
        offset={12}
        className={NODE_TOOLBAR_CLASS}
      >
        {/* 操作区跟随画布缩放（align=center → 锚点顶边中点，贴节点底边）。 */}
        <ZoomScaledToolbar origin="top center">
        <div
          className={`flex min-w-[420px] items-center gap-2 ${CANVAS_NODE_TOOLBAR_PILL_CLASS}`}
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-bg-dark/70 text-text-muted transition-colors hover:bg-bg-dark hover:text-text-dark"
            onClick={onClose}
            title={t('scene360.exit')}
          >
            <X className="h-4 w-4" />
          </button>

          <div className="flex min-w-0 flex-1 items-center gap-1.5 px-2 text-xs text-text-dark">
            <Globe2 className="h-3.5 w-3.5 shrink-0 text-text-muted" />
            <span className="truncate font-medium">{t('scene360.label')}</span>
          </div>

          <AspectRatioDropdown
            value={aspectRatio}
            onChange={setAspectRatio}
            label={t('scene360.aspectRatioLabel')}
          />
          <CreditCostInline display={panoCost.data?.data.display} />

          <button
            type="button"
            className={`${NODE_GENERATE_BUTTON_BASE_CLASS} shrink-0 ${NODE_GENERATE_BUTTON_ENABLED_CLASS}`}
            onClick={handleSubmit}
            title={t('scene360.submit')}
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        </div>
        </ZoomScaledToolbar>
      </ReactFlowNodeToolbar>
    );
  },
);

Scene360Overlay.displayName = 'Scene360Overlay';

interface AspectRatioDropdownProps {
  value: FreezoneScene360AspectRatio;
  onChange: (value: FreezoneScene360AspectRatio) => void;
  label: string;
}

function AspectRatioDropdown({ value, onChange, label }: AspectRatioDropdownProps) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (
        triggerRef.current?.contains(event.target as Node) ||
        popoverRef.current?.contains(event.target as Node)
      ) {
        return;
      }
      setIsOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown, true);
    return () => document.removeEventListener('mousedown', onPointerDown, true);
  }, [isOpen]);

  return (
    <div className="relative shrink-0">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={label}
        title={label}
        onClick={(event) => {
          event.stopPropagation();
          setIsOpen((prev) => !prev);
        }}
        className="inline-flex h-7 items-center gap-1 rounded px-1.5 text-xs font-medium text-text-dark/88 transition-colors hover:text-text-dark"
      >
        <span>{value}</span>
        <ChevronDown className="h-3 w-3 text-text-muted" />
      </button>
      {isOpen && (
        <div
          ref={popoverRef}
          role="listbox"
          className={`absolute bottom-full right-0 z-50 mb-2 min-w-[88px] p-1 ${NODE_FLOATING_PANEL_SURFACE_CLASS}`}
          onClick={(event) => event.stopPropagation()}
        >
          {FREEZONE_SCENE_360_ASPECT_RATIOS.map((ratio) => {
            const isActive = ratio === value;
            return (
              <button
                key={ratio}
                type="button"
                role="option"
                aria-selected={isActive}
                onClick={() => {
                  onChange(ratio);
                  setIsOpen(false);
                }}
                className={`flex w-full items-center rounded px-2.5 py-1.5 text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-white/[0.12] text-text-dark'
                    : 'text-text-dark/50 hover:bg-white/[0.07] hover:text-text-dark/78'
                }`}
              >
                {ratio}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
