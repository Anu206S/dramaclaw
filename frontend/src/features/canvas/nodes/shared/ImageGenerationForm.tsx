// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  ArrowUp,
  Camera,
  ChevronDown,
  Languages,
  Library,
  Loader2,
  Palette,
  X,
} from 'lucide-react';

import type {
  ImageGenCameraSelection,
  ImageGenCount,
  ImageGenNodeData,
  ImageQuality,
  ImageSize,
} from '@/features/canvas/domain/canvasNodes';
import {
  parseAspectRatio,
  pickClosestAspectRatio,
  resolveImageDisplayUrl,
} from '@/features/canvas/application/imageData';
import type { UpstreamContent } from '@/features/canvas/application/ports';
import { useCanvasStore } from '@/stores/canvasStore';
import { ReferenceTextChip } from '@/features/canvas/nodes/shared/ReferenceTextChip';
import {
  PromptMentionEditor,
  type MentionCandidate,
  type PromptMentionEditorHandle,
} from '@/features/canvas/nodes/PromptMentionEditor';
import {
  CAMERA_PICKER_POPOVER_WIDTH,
  CameraPickerPopover,
} from '@/features/canvas/nodes/CameraPickerPopover';
import { StylePickerPopover } from '@/features/canvas/nodes/StylePickerPopover';
import { NodeContextPromptPaletteButton } from '@/features/canvas/nodes/ContextPromptPaletteButton';
import {
  contextPromptPaletteInsertionText,
  type ContextPromptPaletteEntry,
} from '@/features/canvas/nodes/contextPromptPalette';
import { ProviderModelPicker } from '@/features/canvas/ui/ProviderModelPicker';
import { CreditCostPill } from '@/components/credits/credit-visual';
import {
  CANVAS_NODE_INPUT_PLACEHOLDER_CLASS,
} from '@/features/canvas/ui/nodeFrameStyles';
import {
  NODE_COUNT_POPOVER_CLASS,
  NODE_CREDIT_PILL_FLAT_CLASS,
  NODE_FLOATING_PANEL_SURFACE_CLASS,
  NODE_GENERATE_BUTTON_BASE_CLASS,
  NODE_GENERATE_BUTTON_DISABLED_CLASS,
  NODE_GENERATE_BUTTON_ENABLED_CLASS,
  NODE_INLINE_ICON_BUTTON_ACTIVE_CLASS,
  NODE_INLINE_ICON_BUTTON_CLASS,
  NODE_REFERENCE_MEDIA_CHIP_CLASS,
  NODE_REFERENCE_MEDIA_DETACH_CLASS,
  NODE_TEXT_CONTROL_ICON_CLASS,
  NODE_TEXT_CONTROL_TRIGGER_CLASS,
} from '@/features/canvas/ui/nodeControlStyles';

const ASPECT_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'auto', label: '自适应' },
  { value: '1:1', label: '1:1' },
  { value: '9:16', label: '9:16' },
  { value: '16:9', label: '16:9' },
  { value: '3:4', label: '3:4' },
  { value: '4:3', label: '4:3' },
  { value: '3:2', label: '3:2' },
  { value: '2:3', label: '2:3' },
  { value: '4:5', label: '4:5' },
  { value: '5:4', label: '5:4' },
  { value: '21:9', label: '21:9' },
];

const SIZE_OPTIONS: ReadonlyArray<ImageSize> = ['1K', '2K', '4K'];
const COUNT_OPTIONS: ReadonlyArray<ImageGenCount> = [1, 2, 4];

const QUALITY_OPTIONS: ReadonlyArray<{ value: ImageQuality; label: string }> = [
  { value: 'low', label: '低画质' },
  { value: 'medium', label: '标准画质' },
  { value: 'high', label: '高画质' },
];
const IMAGE_PARAM_POPOVER_CLASS =
  `nodrag nowheel absolute bottom-full left-0 z-50 mb-2 w-[300px] p-4 ${NODE_FLOATING_PANEL_SURFACE_CLASS}`;
const IMAGE_PARAM_LABEL_CLASS =
  'mb-2 text-[11px] font-medium uppercase tracking-wide text-text-muted/85';
const IMAGE_PARAM_BUTTON_BASE_CLASS =
  'inline-flex h-8 items-center justify-center rounded-md text-xs transition-colors';
const IMAGE_PARAM_ACTIVE_BUTTON_CLASS =
  'bg-white/[0.13] text-text-dark ring-1 ring-white/24';
const IMAGE_PARAM_IDLE_BUTTON_CLASS =
  'bg-white/[0.07] text-text-muted/95 hover:bg-white/[0.11] hover:text-text-dark';
const IMAGE_PARAM_ROW_CLASS = 'mb-4 flex gap-2';
const NODE_COUNT_OPTION_BASE_CLASS =
  'flex w-full items-center justify-center rounded-[6px] px-3 py-1.5 text-xs transition-colors';

// 图片按自然尺寸算出的比例常是约分形式（如 21:9 会被约成 7:3），不在 ASPECT_OPTIONS 里，
// 直接显示就会出现「7:3」这种列表外的标签。这里退回到「数值最接近的可选比例」（复用
// imageData 的 pickClosestAspectRatio）——chip 标签与下拉里的高亮选项都基于它，保证两边一致。
function resolveNearestAspectOption(aspectRatio: string): { value: string; label: string } {
  const exact = ASPECT_OPTIONS.find((option) => option.value === aspectRatio);
  if (exact) return exact;
  const candidates = ASPECT_OPTIONS.filter((option) => option.value !== 'auto');
  const nearestValue = pickClosestAspectRatio(
    parseAspectRatio(aspectRatio),
    candidates.map((option) => option.value),
  );
  return (
    candidates.find((option) => option.value === nearestValue)
    ?? { value: aspectRatio, label: aspectRatio }
  );
}

interface AspectSizeChipProps {
  aspectRatio: string;
  size: ImageSize;
  quality: ImageQuality;
  /** image2 系模型才显示「画质」选择器，并在标签里带上画质。 */
  showQuality: boolean;
  onChange: (patch: Partial<ImageGenNodeData>) => void;
}

function AspectSizeChip({ aspectRatio, size, quality, showQuality, onChange }: AspectSizeChipProps) {
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

  const nearestAspect = resolveNearestAspectOption(aspectRatio);
  const aspectLabel = nearestAspect.label;
  const qualityLabel = QUALITY_OPTIONS.find((option) => option.value === quality)?.label
    ?? quality;

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setIsOpen((prev) => !prev);
        }}
        className={NODE_TEXT_CONTROL_TRIGGER_CLASS}
      >
        <span>{aspectLabel}</span>
        {showQuality && (
          <>
            <span className="text-text-muted/80">·</span>
            <span>{qualityLabel}</span>
          </>
        )}
        <span className="text-text-muted/80">·</span>
        <span>{size}</span>
        <ChevronDown className="h-3 w-3 text-text-muted/90" />
      </button>
      {isOpen && (
        <div
          ref={popoverRef}
          className={IMAGE_PARAM_POPOVER_CLASS}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
        >
          {showQuality && (
            <>
              <div className={IMAGE_PARAM_LABEL_CLASS}>画质</div>
              <div className={IMAGE_PARAM_ROW_CLASS}>
                {QUALITY_OPTIONS.map((option) => {
                  const isActive = quality === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => onChange({ quality: option.value })}
                      className={`${IMAGE_PARAM_BUTTON_BASE_CLASS} flex-1 ${
                        isActive
                          ? IMAGE_PARAM_ACTIVE_BUTTON_CLASS
                          : IMAGE_PARAM_IDLE_BUTTON_CLASS
                      }`}
                    >
                      {option.label}
                    </button>
                  );
                })}
              </div>
            </>
          )}
          <div className={IMAGE_PARAM_LABEL_CLASS}>分辨率</div>
          <div className={IMAGE_PARAM_ROW_CLASS}>
            {SIZE_OPTIONS.map((option) => {
              const isActive = size === option;
              return (
                <button
                  key={option}
                  type="button"
                  onClick={() => onChange({ size: option })}
                  className={`${IMAGE_PARAM_BUTTON_BASE_CLASS} flex-1 ${
                    isActive
                      ? IMAGE_PARAM_ACTIVE_BUTTON_CLASS
                      : IMAGE_PARAM_IDLE_BUTTON_CLASS
                  }`}
                >
                  {option}
                </button>
              );
            })}
          </div>

          <div className={IMAGE_PARAM_LABEL_CLASS}>比例</div>
          <div className="grid grid-cols-4 gap-2">
            {ASPECT_OPTIONS.map((option) => {
              const isActive = nearestAspect.value === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => onChange({ aspectRatio: option.value })}
                  className={`${IMAGE_PARAM_BUTTON_BASE_CLASS} ${
                    isActive
                      ? IMAGE_PARAM_ACTIVE_BUTTON_CLASS
                      : IMAGE_PARAM_IDLE_BUTTON_CLASS
                  }`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

interface StyleChipProps {
  selectedId: string | null;
  selectedLabel: string | null;
  onChange: (nextId: string | null) => void;
  onOpenChange?: (open: boolean) => void;
}

function StyleChip({ selectedId, selectedLabel, onChange, onOpenChange }: StyleChipProps) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    onOpenChange?.(isOpen);
  }, [isOpen, onOpenChange]);

  useEffect(() => {
    return () => onOpenChange?.(false);
  }, [onOpenChange]);

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

  const isActive = Boolean(selectedId);
  const label = isActive ? selectedLabel ?? '风格' : '风格';

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setIsOpen((prev) => !prev);
        }}
        title={isActive ? selectedLabel ?? undefined : '风格'}
        className={`${NODE_TEXT_CONTROL_TRIGGER_CLASS} max-w-[160px]`}
      >
        <Palette className={`${NODE_TEXT_CONTROL_ICON_CLASS} shrink-0`} />
        <span className="truncate">{label}</span>
      </button>
      {isOpen && (
        <div
          ref={popoverRef}
          className="absolute top-full left-0 z-50 mt-2"
          onClick={(event) => event.stopPropagation()}
        >
          <StylePickerPopover
            selectedId={selectedId}
            onSelect={(nextId) => {
              onChange(nextId);
              setIsOpen(false);
            }}
            onClose={() => setIsOpen(false)}
          />
        </div>
      )}
    </div>
  );
}

interface CameraChipProps {
  selection: ImageGenCameraSelection | null;
  summary: string | null;
  onChange: (next: ImageGenCameraSelection | null) => void;
}

function CameraChip({ selection, summary, onChange }: CameraChipProps) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [popoverPosition, setPopoverPosition] = useState<{
    left: number;
    top: number;
  } | null>(null);

  const syncPopoverPosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const margin = 12;
    setPopoverPosition({
      left: Math.min(
        Math.max(margin, rect.left),
        window.innerWidth - CAMERA_PICKER_POPOVER_WIDTH - margin,
      ),
      top: Math.max(margin, rect.top - 8),
    });
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    syncPopoverPosition();
    const onPointerDown = (event: MouseEvent) => {
      if (
        triggerRef.current?.contains(event.target as Node) ||
        popoverRef.current?.contains(event.target as Node)
      ) {
        return;
      }
      setIsOpen(false);
    };
    const onViewportChange = () => syncPopoverPosition();
    document.addEventListener('mousedown', onPointerDown, true);
    window.addEventListener('resize', onViewportChange);
    window.addEventListener('scroll', onViewportChange, true);
    return () => {
      document.removeEventListener('mousedown', onPointerDown, true);
      window.removeEventListener('resize', onViewportChange);
      window.removeEventListener('scroll', onViewportChange, true);
    };
  }, [isOpen, syncPopoverPosition]);

  const isActive = Boolean(selection) && summary != null;
  const label = isActive && summary ? summary : '摄像机';

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setIsOpen((prev) => !prev);
        }}
        title={isActive ? summary ?? undefined : '摄像机'}
        className={`${NODE_TEXT_CONTROL_TRIGGER_CLASS} max-w-[220px]`}
      >
        <Camera className={`${NODE_TEXT_CONTROL_ICON_CLASS} shrink-0`} />
        <span className="truncate">{label}</span>
      </button>
      {isOpen && popoverPosition && createPortal(
        <div
          ref={popoverRef}
          className="fixed z-[10000]"
          style={{
            left: popoverPosition.left,
            top: popoverPosition.top,
            transform: 'translateY(-100%)',
          }}
          onClick={(event) => event.stopPropagation()}
        >
          <CameraPickerPopover
            selection={selection}
            onConfirm={(next) => {
              onChange(next);
              setIsOpen(false);
            }}
            onClose={() => setIsOpen(false)}
          />
        </div>,
        document.body,
      )}
    </div>
  );
}

interface CountSelectProps {
  value: ImageGenCount;
  onChange: (value: ImageGenCount) => void;
}

function CountSelect({ value, onChange }: CountSelectProps) {
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
        onClick={(event) => {
          event.stopPropagation();
          setIsOpen((prev) => !prev);
        }}
        className={NODE_TEXT_CONTROL_TRIGGER_CLASS}
      >
        <span>{value}张</span>
        <ChevronDown className="h-3 w-3 text-text-muted/90" />
      </button>
      {isOpen && (
        <div
          ref={popoverRef}
          className={NODE_COUNT_POPOVER_CLASS}
        >
          {COUNT_OPTIONS.map((option) => {
            const isActive = option === value;
            return (
              <button
                key={option}
                type="button"
                onClick={() => {
                  onChange(option);
                  setIsOpen(false);
                }}
                className={`${NODE_COUNT_OPTION_BASE_CLASS} ${
                  isActive
                    ? IMAGE_PARAM_ACTIVE_BUTTON_CLASS
                    : 'text-text-muted/95 hover:bg-white/[0.11] hover:text-text-dark'
                }`}
              >
                {option}张
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export interface ImageGenerationFormProps {
  /**
   * 目标节点 id：仅用于本组件内部按钮的定位标识（NodeContextPromptPaletteButton）
   * 和调用 useCanvasStore().updateNodeData 时的 nodeId，不读取任何 React Flow 上下文。
   */
  nodeId: string;

  // ── 参考 / 风格 chips 行 ──
  styleTemplateId: string | null;
  selectedStyleLabel: string | null;
  /** 风格弹层开关：宿主（ImageGenNode）用它临时隐藏下方历史记录条，避免叠层。 */
  onStylePickerOpenChange: (open: boolean) => void;
  onOpenAssetLibrary: () => void;
  upstreamTextContents: readonly UpstreamContent[];
  upstreamImageContents: readonly UpstreamContent[];
  onDetachUpstream: (sourceNodeId: string) => void;

  // ── 提示词编辑器 ──
  // prompt 的 draft 状态、IME 合成态由宿主持有——节点上「生成失败」横幅的重试按钮
  // 需要读同一份 prompt 判断是否可提交，draft 状态若下沉到本组件会导致两处失配。
  prompt: string;
  onPromptChange: (next: string) => void;
  onCompositionStart: () => void;
  onCompositionEnd: (next: string) => void;
  mentionCandidates: MentionCandidate[];
  /** 上游拼接的文本，非空时提示词占位符文案不同。 */
  upstreamTextJoined: string;

  // ── 参数行 ──
  modelId: string;
  aspectRatio: string;
  size: ImageSize;
  quality: ImageQuality;
  /** image2 系模型才显示「画质」选择器。 */
  isImage2: boolean;
  cameraSelection: ImageGenCameraSelection | null;
  cameraSummary: string | null;
  /** 自动提交到主线的系统节点隐藏「生成数量」——数量固定为 1。 */
  showCountSelect: boolean;
  count: ImageGenCount;
  isTranslatingPrompt: boolean;
  isGenerating: boolean;
  onTranslate: () => void;

  // ── 提交 ──
  totalCreditCostDisplay: string | null;
  submitDisabled: boolean;
  onSubmit: () => void;

  /**
   * 纯排版适配位（不改任何字段/行为）：默认在 chips 行右侧留出 `pr-10` 给宿主
   * 叠在右上角的「放大」按钮（ImageGenNode 的 PanelExpandButton）。故事板详情
   * 没有那个按钮，传 true 收掉这段留白，避免 chips 行凭空缺一块。
   */
  compact?: boolean;
}

/**
 * 图片生成节点的**纯表单内容层**：提示词输入 + 参考/风格 chips + 模型选择 +
 * 参数（比例/画质/尺寸/数量）+ 翻译按钮 + 算力 + 提交按钮。不含任何 React Flow
 * 依赖（无 useReactFlow / useNodeId / NodeToolbar / useUpdateNodeInternals），
 * 因此既能挂在画布节点下方的浮动面板里（ImageGenNode + OperationPanelShell），
 * 也能塞进故事板详情之类的独立布局。
 *
 * 面板的「收起/放大」壳体（OperationPanelShell）、在画布上的绝对定位、以及
 * 「生成失败」重试横幅（复用同一个 onSubmit/submitDisabled）都由宿主负责——
 * 这些是节点几何 / 选中态相关的展示逻辑，不属于表单本身。
 */
export const ImageGenerationForm = memo((props: ImageGenerationFormProps) => {
  const {
    nodeId,
    styleTemplateId,
    selectedStyleLabel,
    onStylePickerOpenChange,
    onOpenAssetLibrary,
    upstreamTextContents,
    upstreamImageContents,
    onDetachUpstream,
    prompt,
    onPromptChange,
    onCompositionStart,
    onCompositionEnd,
    mentionCandidates,
    upstreamTextJoined,
    modelId,
    aspectRatio,
    size,
    quality,
    isImage2,
    cameraSelection,
    cameraSummary,
    showCountSelect,
    count,
    isTranslatingPrompt,
    isGenerating,
    onTranslate,
    totalCreditCostDisplay,
    submitDisabled,
    onSubmit,
    compact = false,
  } = props;

  const updateNodeData = useCanvasStore((state) => state.updateNodeData);
  const promptEditorRef = useRef<PromptMentionEditorHandle>(null);

  // 弹层与编辑器同在面板里、编辑器恒已挂载，故插入直接走命令式 API，回调保持稳定引用
  // （无需依赖 prompt，避免每次按键重建回调、连带调色盘按钮重渲染）。
  const insertContextPaletteEntry = useCallback(
    (entry: ContextPromptPaletteEntry) => {
      promptEditorRef.current?.insertTextAtCursor(
        contextPromptPaletteInsertionText(entry),
      );
    },
    [],
  );

  // Hover preview state for the upstream image thumbnails in the reference row.
  // Mirrors the @-mention chip preview UX so users can peek a full-size image
  // without leaving the prompt editor.
  const [refHover, setRefHover] = useState<{ imageUrl: string; rect: DOMRect } | null>(null);
  const refPreviewStyle = useMemo(() => {
    if (!refHover) return null;
    const SIZE = 220;
    const left = Math.min(
      Math.max(8, refHover.rect.left),
      window.innerWidth - SIZE - 8,
    );
    const top = refHover.rect.top - SIZE - 8;
    return { left, top: Math.max(8, top), size: SIZE };
  }, [refHover]);

  return (
    <>
      <div
        className={`flex shrink-0 items-center gap-2 pl-3 pt-3 ${
          compact ? 'pr-3' : 'pr-10'
        }`}
      >
        <StyleChip
          selectedId={styleTemplateId}
          selectedLabel={selectedStyleLabel}
          onChange={(nextId) => updateNodeData(nodeId, { styleTemplateId: nextId })}
          onOpenChange={onStylePickerOpenChange}
        />
        <NodeContextPromptPaletteButton
          nodeId={nodeId}
          onInsert={insertContextPaletteEntry}
        />
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onOpenAssetLibrary();
          }}
          className={`${NODE_TEXT_CONTROL_TRIGGER_CLASS} group/asset px-1.5`}
          title="从资产库选择参考图（人物 / 场景 / 道具）"
        >
          <Library className={`${NODE_TEXT_CONTROL_ICON_CLASS} group-hover/asset:text-text-dark`} />
          <span>资产库</span>
        </button>
        {upstreamTextContents.map((content) => (
          <ReferenceTextChip
            key={content.nodeId}
            nodeId={content.nodeId}
            text={content.text ?? ''}
            sourceLabel={content.displayName ?? content.nodeType}
            onDetach={onDetachUpstream}
          />
        ))}
        {upstreamImageContents.length > 0 && (
          <div className="ml-3 flex shrink-0 items-center gap-1.5">
            {upstreamImageContents.map((content) => {
              const url = resolveImageDisplayUrl(content.imageUrl as string);
              return (
                <div
                  key={`upstream-image-${content.nodeId}`}
                  className={NODE_REFERENCE_MEDIA_CHIP_CLASS}
                  title={`来自上游 · ${content.displayName ?? content.nodeType}`}
                  onMouseEnter={(event) => {
                    setRefHover({
                      imageUrl: url,
                      rect: event.currentTarget.getBoundingClientRect(),
                    });
                  }}
                  onMouseLeave={() => setRefHover(null)}
                >
                  <img
                    src={url}
                    alt=""
                    className="h-full w-full object-cover"
                    draggable={false}
                  />
                  {/* 前端按产品要求不再显示「图片N」数字角标——引用统一呈现为
                      「图片」，序号只存在于提交给后端的 prompt（@图片N）里。 */}
                  <button
                    type="button"
                    title="取消引用此素材"
                    className={NODE_REFERENCE_MEDIA_DETACH_CLASS}
                    onMouseDown={(event) => event.stopPropagation()}
                    onClick={(event) => {
                      event.stopPropagation();
                      setRefHover(null);
                      onDetachUpstream(content.nodeId);
                    }}
                  >
                    <X className="h-3 w-3" strokeWidth={2.5} />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <PromptMentionEditor
        ref={promptEditorRef}
        value={prompt}
        onChange={onPromptChange}
        onCompositionStart={onCompositionStart}
        onCompositionEnd={onCompositionEnd}
        candidates={mentionCandidates}
        placeholder={
          upstreamTextJoined.length > 0
            ? '上游内容已自动接入，可继续补充提示词…'
            : '描述你想要生成的画面内容，@引用素材'
        }
        className={`nodrag nowheel min-h-0 w-full flex-1 overflow-y-auto whitespace-pre-wrap break-words border-none bg-transparent px-3 py-2 text-sm leading-6 text-text-dark outline-none ${CANVAS_NODE_INPUT_PLACEHOLDER_CLASS}`}
      />

      <div className="flex shrink-0 items-center justify-between gap-2 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <ProviderModelPicker
            selectedModelId={modelId}
            onChange={(nextModelId) => updateNodeData(nodeId, { model: nextModelId })}
            popoverPlacement="top"
          />
          <AspectSizeChip
            aspectRatio={aspectRatio}
            size={size}
            quality={quality}
            showQuality={isImage2}
            onChange={(patch) => updateNodeData(nodeId, patch)}
          />
          <CameraChip
            selection={cameraSelection}
            summary={cameraSummary}
            onChange={(next) => updateNodeData(nodeId, { cameraSelection: next })}
          />
          {showCountSelect && (
            <CountSelect
              value={count}
              onChange={(nextCount) => updateNodeData(nodeId, { count: nextCount })}
            />
          )}
          <button
            type="button"
            title="翻译提示词（中英文互译）"
            disabled={isTranslatingPrompt || isGenerating || prompt.trim().length === 0}
            onClick={(event) => {
              event.stopPropagation();
              onTranslate();
            }}
            className={`${NODE_INLINE_ICON_BUTTON_CLASS} ${
              isTranslatingPrompt
                ? NODE_INLINE_ICON_BUTTON_ACTIVE_CLASS
                : ''
            }`}
          >
            {isTranslatingPrompt ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Languages className="h-4 w-4" />
            )}
          </button>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <CreditCostPill
            display={totalCreditCostDisplay}
            disabled={submitDisabled}
            className={NODE_CREDIT_PILL_FLAT_CLASS}
          />
          <button
            type="button"
            disabled={submitDisabled}
            title="生成"
            onClick={(event) => {
              event.stopPropagation();
              onSubmit();
            }}
            className={`${NODE_GENERATE_BUTTON_BASE_CLASS} ${
              submitDisabled
                ? NODE_GENERATE_BUTTON_DISABLED_CLASS
                : NODE_GENERATE_BUTTON_ENABLED_CLASS
            }`}
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        </div>
      </div>

      {refHover && refPreviewStyle
        && createPortal(
          <div
            className="pointer-events-none fixed z-[10001] overflow-hidden rounded-lg border border-white/15 bg-surface-dark/95 shadow-xl"
            style={{
              left: refPreviewStyle.left,
              top: refPreviewStyle.top,
              width: refPreviewStyle.size,
              height: refPreviewStyle.size,
            }}
          >
            <img
              src={refHover.imageUrl}
              alt=""
              className="h-full w-full object-cover"
              draggable={false}
            />
          </div>,
          document.body,
        )}
    </>
  );
});

ImageGenerationForm.displayName = 'ImageGenerationForm';
