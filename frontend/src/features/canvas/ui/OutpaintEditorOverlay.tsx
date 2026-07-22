// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { NodeToolbar as ReactFlowNodeToolbar, Position } from '@xyflow/react';
import {
  ArrowUp,
  Check,
  ChevronDown,
  Image as ImageIcon,
  RectangleHorizontal,
  RectangleVertical,
  Sparkles,
  Square,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  DEFAULT_NODE_WIDTH,
  type CanvasNode,
} from '@/features/canvas/domain/canvasNodes';
import { useCanvasStore } from '@/stores/canvasStore';
import { type FreezoneOutpaintAspectRatio } from '@/api/ops';
import { outpaintImage } from '@/features/canvas/application/imageOutpaint';
import {
  DEFAULT_SHARED_MODEL_ID,
  ProviderModelPicker,
  SHARED_MODELS,
} from '@/features/canvas/ui/ProviderModelPicker';
import { useFreezoneImageModels } from '@/features/canvas/hooks/useFreezoneImageModels';
import { CreditCostPill } from '@/components/credits/credit-visual';
import { useGenerationCreditCost } from '@/lib/queries/generation-credit-cost';
import { NODE_TOOLBAR_CLASS } from './nodeToolbarConfig';
import { CANVAS_NODE_TOOLBAR_PILL_CLASS } from './nodeFrameStyles';
import {
  NODE_CREDIT_PILL_FLAT_CLASS,
  NODE_GENERATE_BUTTON_BASE_CLASS,
  NODE_GENERATE_BUTTON_ENABLED_CLASS,
  NODE_GENERATE_BUTTON_DISABLED_CLASS,
} from './nodeControlStyles';

const OUTPAINT_IMAGE_SIZES = ['1K', '2K', '4K'] as const;
type OutpaintImageSize = (typeof OUTPAINT_IMAGE_SIZES)[number];

const OUTPAINT_NUM_IMAGES = [1, 2, 3, 4] as const;
type OutpaintNumImages = (typeof OUTPAINT_NUM_IMAGES)[number];

const OUTPAINT_ASPECT_OPTIONS: {
  value: FreezoneOutpaintAspectRatio;
  ratio: number | null; // null = preserve original
  i18nKey: string;
  Icon: typeof RectangleHorizontal;
}[] = [
  { value: 'original', ratio: null, i18nKey: 'outpaintEditor.aspect.original', Icon: ImageIcon },
  { value: '1:1', ratio: 1, i18nKey: 'outpaintEditor.aspect.s1_1', Icon: Square },
  { value: '4:3', ratio: 4 / 3, i18nKey: 'outpaintEditor.aspect.s4_3', Icon: RectangleHorizontal },
  { value: '3:4', ratio: 3 / 4, i18nKey: 'outpaintEditor.aspect.s3_4', Icon: RectangleVertical },
  { value: '16:9', ratio: 16 / 9, i18nKey: 'outpaintEditor.aspect.s16_9', Icon: RectangleHorizontal },
  { value: '9:16', ratio: 9 / 16, i18nKey: 'outpaintEditor.aspect.s9_16', Icon: RectangleVertical },
];

function imageModelSupportsQuality(apiModel: string | null | undefined): boolean {
  if (!apiModel) return false;
  const normalized = apiModel.toLowerCase();
  return (
    normalized === 'gpt-image-2'
    || normalized === 'image-2'
    || normalized === 'image-2-official'
    || normalized.includes('gpt-image')
  );
}

interface OutpaintEditorOverlayProps {
  node: CanvasNode;
  imageSource: string;
  onClose: () => void;
}

export const OutpaintEditorOverlay = memo(
  ({ node, imageSource, onClose }: OutpaintEditorOverlayProps) => {
    const { t } = useTranslation();
    const setSelectedNode = useCanvasStore((state) => state.setSelectedNode);

    const [aspectRatio, setAspectRatio] =
      useState<FreezoneOutpaintAspectRatio>('original');
    const [imageSize, setImageSize] = useState<OutpaintImageSize>('2K');
    const [numImages, setNumImages] = useState<OutpaintNumImages>(1);
    const [modelId, setModelId] = useState<string>(DEFAULT_SHARED_MODEL_ID);
    const { models: availableModels } = useFreezoneImageModels();
    const [isSubmitting, setIsSubmitting] = useState(false);
    const selectedModel =
      availableModels.find((m) => m.id === modelId)
      ?? availableModels[0]
      ?? SHARED_MODELS.find((m) => m.id === modelId);
    const creditCost = useGenerationCreditCost(
      'image_selection',
      selectedModel?.apiModel ?? null,
      {
        surface: 'canvas',
        params: imageModelSupportsQuality(selectedModel?.apiModel)
          ? { size: imageSize, quality: 'medium' }
          : { size: imageSize },
        quantity: Math.min(Math.max(numImages, 1), 4),
      },
    );

    const nodeWidth =
      typeof node.measured?.width === 'number'
        ? node.measured.width
        : typeof node.width === 'number'
          ? node.width
          : DEFAULT_NODE_WIDTH;
    const nodeHeight =
      typeof node.measured?.height === 'number'
        ? node.measured.height
        : typeof node.height === 'number'
          ? node.height
          : nodeWidth;

    const frame = useMemo(() => {
      const option = OUTPAINT_ASPECT_OPTIONS.find((o) => o.value === aspectRatio);
      const targetRatio = option?.ratio ?? null;
      if (targetRatio === null) {
        return { width: nodeWidth, height: nodeHeight };
      }
      const nodeRatio = nodeWidth / nodeHeight;
      // Keep the original image at its native size; extend only the dimension
      // that needs to grow so the frame still contains it.
      if (targetRatio >= nodeRatio) {
        // Target is wider → grow horizontally.
        return { width: nodeHeight * targetRatio, height: nodeHeight };
      }
      // Target is taller → grow vertically.
      return { width: nodeWidth, height: nodeWidth / targetRatio };
    }, [aspectRatio, nodeHeight, nodeWidth]);

    const verticalExtension = Math.max(0, (frame.height - nodeHeight) / 2);
    const horizontalExtension = Math.max(0, (frame.width - nodeWidth) / 2);
    const bottomToolbarOffset = verticalExtension + 12;

    const handleSubmit = useCallback(async () => {
      if (isSubmitting) return;
      const apiModel = selectedModel?.apiModel ?? modelId;

      setIsSubmitting(true);
      try {
        const result = outpaintImage(node.id, imageSource, {
          displayName: t('outpaintEditor.title'),
          targetAspectRatio: aspectRatio,
          imageSize,
          numImages,
          model: apiModel,
        });
        if (!result) return;
        setSelectedNode(result.nodeIds[0]);
        onClose();
      } finally {
        setIsSubmitting(false);
      }
    }, [
      aspectRatio,
      imageSize,
      imageSource,
      isSubmitting,
      modelId,
      node.id,
      numImages,
      onClose,
      selectedModel,
      setSelectedNode,
      t,
    ]);

    return (
      <>
        {/* Frame overlay anchored at the node's top edge; the inner div uses
            absolute positioning to draw a rectangle centered on the node. */}
        <ReactFlowNodeToolbar
          nodeId={node.id}
          isVisible
          position={Position.Top}
          align="center"
          offset={0}
          className={`${NODE_TOOLBAR_CLASS} pointer-events-none`}
        >
          <div className="relative" style={{ width: 0, height: 0 }}>
            <div
              className="pointer-events-none absolute overflow-hidden rounded-lg border border-cyan-200/30 bg-cyan-200/[0.025] shadow-[0_0_0_1px_rgba(34,211,238,0.08)]"
              style={{
                width: frame.width,
                height: frame.height,
                left: '50%',
                top: nodeHeight / 2,
                transform: 'translate(-50%, -50%)',
              }}
            >
              {verticalExtension > 0 && (
                <>
                  <div
                    className="absolute inset-x-0 top-0 bg-cyan-200/[0.055]"
                    style={{ height: verticalExtension }}
                  />
                  <div
                    className="absolute inset-x-0 bottom-0 bg-cyan-200/[0.055]"
                    style={{ height: verticalExtension }}
                  />
                </>
              )}
              {horizontalExtension > 0 && (
                <>
                  <div
                    className="absolute inset-y-0 left-0 bg-cyan-200/[0.055]"
                    style={{ width: horizontalExtension }}
                  />
                  <div
                    className="absolute inset-y-0 right-0 bg-cyan-200/[0.055]"
                    style={{ width: horizontalExtension }}
                  />
                </>
              )}
            </div>
          </div>
        </ReactFlowNodeToolbar>

        <ReactFlowNodeToolbar
          nodeId={node.id}
          isVisible
          position={Position.Bottom}
          align="center"
          offset={bottomToolbarOffset}
          className={NODE_TOOLBAR_CLASS}
        >
          <div
            className={`flex items-center gap-1 ${CANVAS_NODE_TOOLBAR_PILL_CLASS}`}
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-text-muted transition-colors hover:bg-white/[0.06] hover:text-text-dark"
              onClick={onClose}
              title={t('outpaintEditor.exit')}
            >
              <X className="h-4 w-4" />
            </button>

            <ProviderModelPicker selectedModelId={modelId} onChange={setModelId} />
            <AspectRatioPicker value={aspectRatio} onChange={setAspectRatio} />
            <SimpleSegmentedDropdown<OutpaintImageSize>
              value={imageSize}
              options={OUTPAINT_IMAGE_SIZES}
              onChange={setImageSize}
              renderLabel={(v) => v}
              titleI18nKey="outpaintEditor.qualityLabel"
            />
            <SimpleSegmentedDropdown<OutpaintNumImages>
              value={numImages}
              options={OUTPAINT_NUM_IMAGES}
              onChange={setNumImages}
              renderLabel={(v) => t('outpaintEditor.numImages', { count: v })}
              titleI18nKey="outpaintEditor.numImagesLabel"
            />
            <CreditCostPill
              display={creditCost.data?.data.display}
              className={NODE_CREDIT_PILL_FLAT_CLASS}
            />

            <button
              type="button"
              onClick={handleSubmit}
              disabled={isSubmitting}
              className={`shrink-0 ${NODE_GENERATE_BUTTON_BASE_CLASS} ${
                isSubmitting
                  ? NODE_GENERATE_BUTTON_DISABLED_CLASS
                  : NODE_GENERATE_BUTTON_ENABLED_CLASS
              }`}
              title={t('outpaintEditor.submit')}
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          </div>
        </ReactFlowNodeToolbar>
      </>
    );
  },
);

OutpaintEditorOverlay.displayName = 'OutpaintEditorOverlay';

interface AspectRatioPickerProps {
  value: FreezoneOutpaintAspectRatio;
  onChange: (next: FreezoneOutpaintAspectRatio) => void;
}

function AspectRatioPicker({ value, onChange }: AspectRatioPickerProps) {
  const { t } = useTranslation();
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

  const selected = OUTPAINT_ASPECT_OPTIONS.find((o) => o.value === value)
    ?? OUTPAINT_ASPECT_OPTIONS[0];
  const SelectedIcon = selected.Icon;

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="inline-flex h-8 items-center gap-1 rounded-full px-2.5 text-xs text-text-dark transition-colors hover:bg-white/[0.06]"
      >
        <SelectedIcon className="h-3.5 w-3.5 text-text-muted" />
        <span className="font-medium">{t(selected.i18nKey)}</span>
        <ChevronDown className="h-3 w-3 text-text-muted" />
      </button>
      {isOpen && (
        <div
          ref={popoverRef}
          className="absolute bottom-full left-1/2 z-50 mb-2 w-[180px] -translate-x-1/2 rounded-xl border border-white/10 bg-surface-dark/95 p-2 shadow-2xl backdrop-blur-md"
          onPointerDown={(event) => event.stopPropagation()}
        >
          <div className="mb-1 px-2 py-1 text-[11px] uppercase tracking-wide text-text-muted">
            {t('outpaintEditor.aspectLabel')}
          </div>
          <div className="flex flex-col">
            {OUTPAINT_ASPECT_OPTIONS.map((option) => {
              const Icon = option.Icon;
              const isActive = option.value === value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => {
                    onChange(option.value);
                    setIsOpen(false);
                  }}
                  className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-white/[0.12] text-text-dark'
                      : 'text-text-muted hover:bg-white/[0.08] hover:text-text-dark'
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{t(option.i18nKey)}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

interface SimpleSegmentedDropdownProps<T extends string | number> {
  value: T;
  options: readonly T[];
  onChange: (next: T) => void;
  renderLabel: (value: T) => string;
  titleI18nKey: string;
}

function SimpleSegmentedDropdown<T extends string | number>({
  value,
  options,
  onChange,
  renderLabel,
  titleI18nKey,
}: SimpleSegmentedDropdownProps<T>) {
  const { t } = useTranslation();
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
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="inline-flex h-8 items-center gap-1 rounded-full px-2.5 text-xs text-text-dark transition-colors hover:bg-white/[0.06]"
      >
        <Sparkles className="h-3.5 w-3.5 text-text-muted" />
        <span className="font-medium">{renderLabel(value)}</span>
        <ChevronDown className="h-3 w-3 text-text-muted" />
      </button>
      {isOpen && (
        <div
          ref={popoverRef}
          className="absolute bottom-full left-1/2 z-50 mb-2 w-[160px] -translate-x-1/2 rounded-xl border border-white/10 bg-surface-dark/95 p-2 shadow-2xl backdrop-blur-md"
          onPointerDown={(event) => event.stopPropagation()}
        >
          <div className="mb-1 px-2 py-1 text-[11px] uppercase tracking-wide text-text-muted">
            {t(titleI18nKey)}
          </div>
          <div className="flex flex-col">
            {options.map((option) => {
              const isActive = option === value;
              return (
                <button
                  key={String(option)}
                  type="button"
                  onClick={() => {
                    onChange(option);
                    setIsOpen(false);
                  }}
                  className={`flex items-center justify-between rounded-md px-2 py-1.5 text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-white/[0.12] text-text-dark'
                      : 'text-text-muted hover:bg-white/[0.08] hover:text-text-dark'
                  }`}
                >
                  <span>{renderLabel(option)}</span>
                  {isActive && <Check className="h-3 w-3" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
