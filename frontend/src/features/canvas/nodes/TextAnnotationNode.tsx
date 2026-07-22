// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Handle, Position, useReactFlow, type NodeProps } from '@xyflow/react';
import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import {
  AlignJustify,
  ArrowUp,
  FileText,
  Image as ImageIcon,
  Languages,
  Loader2,
  Music,
  Music2,
  PlaySquare,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  CANVAS_NODE_TYPES,
  type TextAnnotationNodeData,
  type TextNodeMode,
} from '@/features/canvas/domain/canvasNodes';
import { resolveImageDisplayUrl } from '@/features/canvas/application/imageData';
import { isSystemManagedNodeData } from '@/features/canvas/domain/mainlineNodeFlags';
import { resolveNodeDisplayName } from '@/features/canvas/domain/nodeDisplay';
import { NodeHeader, NODE_HEADER_FLOATING_POSITION_CLASS } from '@/features/canvas/ui/NodeHeader';
import { NodeResizeHandle } from '@/features/canvas/ui/NodeResizeHandle';
import { NodeGenerationOverlay } from '@/features/canvas/ui/NodeGenerationOverlay';
import {
  CANVAS_NODE_INPUT_BODY_FRAME_CLASS,
  CANVAS_NODE_INPUT_BODY_SELECTED_FRAME_CLASS,
  CANVAS_NODE_INPUT_FRAME_CLASS,
  CANVAS_NODE_INPUT_PLACEHOLDER_CLASS,
  CANVAS_NODE_INPUT_SURFACE_CLASS,
} from '@/features/canvas/ui/nodeFrameStyles';
import { useCanvasStore, useIsBoxSelecting } from '@/stores/canvasStore';
import { translateNodeText } from '@/features/canvas/application/translateText';
import {
  publishNodeActionAccepted,
  publishNodeActionError,
  publishNodeActionSuccess,
  subscribeNodeAction,
} from '@/features/canvas/application/nodeActionResult';
import {
  REVERSE_PROMPT_DURATION_MS,
  resolveUpstreamImageUrl,
  runTextImageToPrompt,
} from '@/features/canvas/application/textImageToPrompt';
import {
  applyTextNodeMode,
  IMAGE_TO_PROMPT_DEFAULT_CONTENT,
  TEXT_NODE_COMPACT_MODES,
  TEXT_NODE_REAL_MODES,
} from '@/features/canvas/application/textNodeModes';
import {
  resolveTextNodeDownstreamVideoNodeId,
  submitTextToVideo,
} from '@/features/canvas/application/textToVideoSubmit';
import { useNodeGenerationTaskState } from '@/features/canvas/application/useNodeGenerationTaskState';
import { joinUpstreamText } from '@/features/canvas/application/graphContentResolver';
import { useUpstreamContents } from '@/features/canvas/application/useUpstreamGraph';
import { generateWorkflowText } from '@/features/canvas/application/workflowRecipeRuntime';
import { readUrl } from '@/lib/url-params';
import {
  DEFAULT_SHARED_MODEL_ID,
  DEFAULT_VIDEO_MODEL_ID,
  ProviderModelPicker,
} from '@/features/canvas/ui/ProviderModelPicker';
import {
  NODE_GENERATE_BUTTON_BASE_CLASS,
  NODE_GENERATE_BUTTON_DISABLED_CLASS,
  NODE_GENERATE_BUTTON_ENABLED_CLASS,
  NODE_INLINE_ICON_BUTTON_ACTIVE_CLASS,
  NODE_INLINE_ICON_BUTTON_CLASS,
} from '@/features/canvas/ui/nodeControlStyles';
import { useFreezoneVideoModels } from '@/features/canvas/hooks/useFreezoneVideoModels';
import { CreditCostInline } from '@/components/credit-cost-inline';
import { useGenerationCreditCost } from '@/lib/queries/generation-credit-cost';

type TextAnnotationNodeProps = NodeProps & {
  id: string;
  data: TextAnnotationNodeData;
  selected?: boolean;
};

const DEFAULT_WIDTH = 440;
const DEFAULT_HEIGHT = 220;
const COMPACT_DEFAULT_HEIGHT = 320;
const MIN_WIDTH = 380;
const MIN_HEIGHT = 240;
const COMPACT_MIN_HEIGHT = 240;
const MAX_WIDTH = 900;
const MAX_HEIGHT = 1200;

const PICKER_INSET = 32;
const COMPACT_OPS_PANEL_HEIGHT = 140;
const COMPACT_OPS_PANEL_GAP = 12;
const COMPACT_OPS_PANEL_MIN_WIDTH = 480;

const MODES: ReadonlyArray<{
  key: TextNodeMode;
  icon: typeof FileText;
  labelKey: string;
}> = [
  { key: 'writing', icon: FileText, labelKey: 'node.textNode.modes.writing' },
  { key: 'textToVideo', icon: PlaySquare, labelKey: 'node.textNode.modes.textToVideo' },
  { key: 'imageToPrompt', icon: ImageIcon, labelKey: 'node.textNode.modes.imageToPrompt' },
  { key: 'textToMusic', icon: Music, labelKey: 'node.textNode.modes.textToMusic' },
  { key: 'textToMusicGen', icon: Music2, labelKey: 'node.textNode.modes.textToMusicGen' },
];

const EDIT_VIEW_ZOOM = 1.4;

export const TextAnnotationNode = memo(({
  id,
  data,
  selected,
  width,
  height,
}: TextAnnotationNodeProps) => {
  const { t } = useTranslation();
  const reactFlow = useReactFlow();
  const setSelectedNode = useCanvasStore((state) => state.setSelectedNode);
  const isBoxSelecting = useIsBoxSelecting();
  const updateNodeData = useCanvasStore((state) => state.updateNodeData);
  const deleteEdge = useCanvasStore((state) => state.deleteEdge);
  const content = typeof data.content === 'string' ? data.content : '';
  const instruction = typeof data.instruction === 'string' ? data.instruction : '';
  const mode: TextNodeMode =
    data.mode && TEXT_NODE_REAL_MODES.has(data.mode) ? data.mode : 'writing';
  // 已从能力 picker 选过一次(如「文字生成音乐」)：恒为纯文本编辑区,空内容也不再弹「试试」。
  const pickerDismissed = Boolean(data.pickerDismissed);
  const modelId = typeof data.model === 'string' && data.model.length > 0
    ? data.model
    : DEFAULT_SHARED_MODEL_ID;
  // 文生视频默认模型取「视频模型接口返回的第一个」，而非文本节点的图像默认 id。
  const { models: videoModels } = useFreezoneVideoModels();
  const reversePromptCost = useGenerationCreditCost(
    mode === 'imageToPrompt' ? 'freezone_image_reverse_prompt' : '',
    null,
    { surface: 'canvas' },
  );
  const { isGenerating } = useNodeGenerationTaskState(data);
  const upstreamContents = useUpstreamContents(id);
  const upstreamTextJoined = useMemo(
    () => joinUpstreamText(upstreamContents),
    [upstreamContents],
  );
  // referenceOnly: 节点被作为上游引用素材使用（脚本节点 spawn 出来的）。
  // 复用 compact 视图（只渲染编辑卡片），同时 selected ops panel 也不显示。
  const isReferenceOnly = Boolean(data.referenceOnly);
  const isSystemManaged = isSystemManagedNodeData(data);
  const isCompactView = isReferenceOnly || TEXT_NODE_COMPACT_MODES.has(mode);
  const [isEditingContent, setIsEditingContent] = useState(false);
  const editTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const resolvedTitle = resolveNodeDisplayName(CANVAS_NODE_TYPES.textAnnotation, data);
  const minHeightForView = isCompactView ? COMPACT_MIN_HEIGHT : MIN_HEIGHT;
  const defaultHeightForView = isCompactView ? COMPACT_DEFAULT_HEIGHT : DEFAULT_HEIGHT;
  const resolvedWidth = Math.max(MIN_WIDTH, Math.round(width ?? DEFAULT_WIDTH));
  const resolvedHeight = Math.max(minHeightForView, Math.round(height ?? defaultHeightForView));

  // Reactive lookup of the upstream image URL (e.g. uploaded reference image
  // for `imageToPrompt` mode). Re-evaluates whenever edges/nodes change.
  const upstreamImageUrl = useCanvasStore((state) => {
    const edge = state.edges.find((e) => e.target === id);
    if (!edge) return null;
    const node = state.nodes.find((n) => n.id === edge.source);
    return resolveUpstreamImageUrl(node?.data);
  });

  // 取消关联上游参考图：删掉指向本节点的那根连线（缩略图只在该边的源带图时
  // 才显示，所以这里删第一条 target===id 的边即对应当前展示的素材）。
  const handleDetachUpstreamImage = useCallback(() => {
    const state = useCanvasStore.getState();
    const edge = state.edges.find((e) => e.target === id);
    if (edge) {
      deleteEdge(edge.id);
    }
  }, [id, deleteEdge]);

  // libtv-style edit mode: dbl-click the preview card → zoom canvas to 200%
  // centered on this node and focus a fullsize textarea. Escape / blur exits.
  const enterEditMode = useCallback(() => {
    if (isSystemManaged) return;
    const node = reactFlow.getNode(id);
    if (node) {
      const w = (node.measured?.width ?? width ?? DEFAULT_WIDTH);
      const h = (node.measured?.height ?? height ?? DEFAULT_HEIGHT);
      // 组内成员的 node.position 是「相对父组」的坐标，而 setCenter 需要绝对画布坐标。
      // 用 internalNode 的 positionAbsolute（无父组时等于 position），否则双击组里的
      // 节点会把视野按组原点的偏移量平移到别处。
      const absolute =
        reactFlow.getInternalNode(id)?.internals.positionAbsolute ?? node.position;
      const cx = absolute.x + w / 2;
      const cy = absolute.y + h / 2;
      void reactFlow.setCenter(cx, cy, { zoom: EDIT_VIEW_ZOOM, duration: 280 });
    }
    setIsEditingContent(true);
  }, [height, id, isSystemManaged, reactFlow, width]);

  useEffect(() => {
    if (isSystemManaged && isEditingContent) {
      setIsEditingContent(false);
    }
  }, [isEditingContent, isSystemManaged]);

  useEffect(() => {
    if (!isEditingContent) return;
    // Focus on next tick so the textarea exists after the swap.
    const timer = window.setTimeout(() => {
      editTextareaRef.current?.focus();
      const len = editTextareaRef.current?.value.length ?? 0;
      editTextareaRef.current?.setSelectionRange(len, len);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [isEditingContent]);

  // 能力选择（含派生下游/上游节点）走 application/textNodeModes——故事板详情复用
  // 同一份实现；enterEditMode 的画布缩放语义只属于工作流，所以留在这里执行。
  const handlePickMode = useCallback((nextMode: TextNodeMode) => {
    const { enterEdit } = applyTextNodeMode(id, nextMode);
    if (enterEdit) enterEditMode();
  }, [enterEditMode, id]);

  const runRecipeText = useCallback(async (): Promise<{ content?: string }> => {
    updateNodeData(id, {
      isGenerating: true,
      generationStartedAt: Date.now(),
      generationError: null,
    });
    try {
      const generated = await generateWorkflowText({
        nodeData: data,
        nodePrompt: content,
        upstreamText: upstreamTextJoined,
        upstreamContents,
      });
      updateNodeData(id, {
        content: generated,
        workflowTextGenerated: true,
        isGenerating: false,
        generationStartedAt: null,
      });
      return { content: generated };
    } catch (error) {
      updateNodeData(id, {
        isGenerating: false,
        generationStartedAt: null,
        generationError: error instanceof Error ? error.message : '文本生成失败',
      });
      throw error;
    }
  }, [content, data, id, updateNodeData, upstreamContents, upstreamTextJoined]);

  useEffect(() => {
    return subscribeNodeAction(({ nodeId, action, requestId }) => {
      if (nodeId === id && action === 'generate_text') {
        publishNodeActionAccepted(requestId, id, action);
        void runRecipeText()
          .then((output) => publishNodeActionSuccess(requestId, id, action, output))
          .catch((error) => publishNodeActionError(requestId, id, action, error));
        return;
      }
      if (nodeId !== id || action !== 'generate_text_video') return;
      publishNodeActionAccepted(requestId, id, action);
      // 编排走 application/textToVideoSubmit（与故事板详情同一条链路）。helper 只回报
      // 承载产物的节点 id 与失败原因，产物 url 仍从那个下游视频节点上回读。
      void submitTextToVideo(id, {
        content,
        fallbackModelId: videoModels[0]?.id ?? DEFAULT_VIDEO_MODEL_ID,
      })
        .then((result) => {
          if (result.error) {
            publishNodeActionError(requestId, id, action, new Error(result.error));
            return;
          }
          const resultNodeId = result.nodeIds[0] ?? resolveTextNodeDownstreamVideoNodeId(id);
          const resultNode = resultNodeId
            ? useCanvasStore.getState().nodes.find((node) => node.id === resultNodeId)
            : null;
          const videoUrl = resultNode?.type === CANVAS_NODE_TYPES.video
            && typeof resultNode.data.videoUrl === 'string'
            ? resultNode.data.videoUrl
            : undefined;
          publishNodeActionSuccess(requestId, id, action, videoUrl ? { videoUrl } : {});
        })
        .catch((error) => publishNodeActionError(requestId, id, action, error));
    });
  }, [content, id, runRecipeText, videoModels]);

  const textPlaceholder = t('node.textNode.placeholder');
  const hasUserContent = content.trim().length > 0 && content.trim() !== textPlaceholder.trim();

  const handleSubmit = useCallback(() => {
    if (isGenerating) return;
    if (mode === 'imageToPrompt') {
      void runTextImageToPrompt(id);
      return;
    }
    if (mode === 'textToVideo') {
      void submitTextToVideo(id, {
        content,
        fallbackModelId: videoModels[0]?.id ?? DEFAULT_VIDEO_MODEL_ID,
      });
      return;
    }
    if (!hasUserContent) return;
    console.info('[text-node] submit stub', { id, mode, model: modelId, content });
  }, [content, hasUserContent, id, isGenerating, mode, modelId, videoModels]);

  const submitDisabled = isGenerating
    || (mode !== 'imageToPrompt' && !hasUserContent);
  // Inner panels stay neutral regardless of selection — the React Flow node
  // wrapper already shows the active state as an outer outline. Doubling it
  // up on the inner cards (libtv-style reference shows neutral borders only)
  // looks busy.
  const inputBodyToneClass = `${CANVAS_NODE_INPUT_SURFACE_CLASS} ${
    selected ? CANVAS_NODE_INPUT_BODY_SELECTED_FRAME_CLASS : CANVAS_NODE_INPUT_BODY_FRAME_CLASS
  }`;
  const inputPanelToneClass = `${CANVAS_NODE_INPUT_SURFACE_CLASS} ${CANVAS_NODE_INPUT_FRAME_CLASS}`;

  return (
    <div
      className="group relative h-full w-full overflow-visible"
      style={{ width: resolvedWidth, height: resolvedHeight }}
      onClick={() => setSelectedNode(id)}
    >
      <Handle
        type="target"
        position={Position.Left}
        id="target"
        className="!h-2 !w-2 !border-0 !bg-[rgb(148,163,184)]"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="source"
        className="!h-2 !w-2 !border-0 !bg-[rgb(148,163,184)]"
      />

      <NodeHeader
        className={NODE_HEADER_FLOATING_POSITION_CLASS}
        icon={<FileText className="h-4 w-4" />}
        titleText={resolvedTitle}
        editable={!isSystemManaged}
        onTitleChange={(nextTitle) => updateNodeData(id, { displayName: nextTitle })}
      />

      <NodeResizeHandle
        minWidth={MIN_WIDTH}
        minHeight={minHeightForView}
        maxWidth={MAX_WIDTH}
        maxHeight={MAX_HEIGHT}
      />

      {!isCompactView && selected && !isBoxSelecting && !isReferenceOnly && !isSystemManaged && !isEditingContent && (
        <WritingOpsPanel
          nodeId={id}
          content={content}
          isGenerating={isGenerating}
          width={resolvedWidth}
        />
      )}

      {isCompactView ? (
        <>
          <div
            className={`flex h-full w-full flex-col items-center justify-center rounded-[var(--node-radius)] border transition-colors ${inputBodyToneClass}`}
            onDoubleClick={(event) => {
              if (isEditingContent || isSystemManaged) return;
              event.stopPropagation();
              enterEditMode();
            }}
          >
            {isEditingContent ? (
              <textarea
                ref={editTextareaRef}
                value={content}
                onChange={(event) => updateNodeData(id, {
                  content: event.target.value,
                  workflowTextGenerated: false,
                })}
                onMouseDown={(event) => event.stopPropagation()}
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => {
                  event.stopPropagation();
                  if (event.key === 'Escape') {
                    setIsEditingContent(false);
                    editTextareaRef.current?.blur();
                  }
                }}
                onBlur={() => setIsEditingContent(false)}
                placeholder={textPlaceholder}
                className={`ui-scrollbar nodrag nowheel h-full w-full resize-none border-none bg-transparent px-4 py-4 text-sm leading-6 text-text-dark outline-none ${CANVAS_NODE_INPUT_PLACEHOLDER_CLASS}`}
              />
            ) : hasUserContent ? (
              <div className="ui-scrollbar nowheel max-h-full w-full overflow-y-auto px-4 py-4 text-sm leading-6 text-text-dark">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm, remarkBreaks]}
                  components={{
                    h1: ({ ...props }) => <h1 className="mb-1 mt-2 text-base font-semibold" {...props} />,
                    h2: ({ ...props }) => <h2 className="mb-1 mt-2 text-sm font-semibold" {...props} />,
                    h3: ({ ...props }) => <h3 className="mb-1 mt-1 text-sm font-semibold" {...props} />,
                    p: ({ ...props }) => <p className="my-1" {...props} />,
                    strong: ({ ...props }) => <strong className="font-semibold text-text-dark" {...props} />,
                    em: ({ ...props }) => <em className="italic" {...props} />,
                    ul: ({ ...props }) => <ul className="my-1 ml-5 list-disc" {...props} />,
                    ol: ({ ...props }) => <ol className="my-1 ml-5 list-decimal" {...props} />,
                    li: ({ ...props }) => <li className="my-0.5" {...props} />,
                    code: ({ ...props }) => (
                      <code className="rounded bg-white/10 px-1 py-0.5 text-xs" {...props} />
                    ),
                    hr: () => <hr className="my-2 border-white/10" />,
                  }}
                >
                  {content}
                </ReactMarkdown>
              </div>
            ) : (
              <AlignJustify className="h-12 w-12 stroke-[1.5] text-text-muted/40" />
            )}
            {isGenerating && (
              <NodeGenerationOverlay
                startedAt={data.generationStartedAt}
                durationMs={REVERSE_PROMPT_DURATION_MS}
                hasBackground={hasUserContent}
              />
            )}
          </div>

          {selected && !isBoxSelecting && !isReferenceOnly && !isSystemManaged && !isEditingContent && (
            <div
              className={`nodrag absolute left-1/2 z-[300] flex -translate-x-1/2 flex-col rounded-[var(--node-radius)] border ${inputPanelToneClass}`}
              style={{
                top: `calc(100% + ${COMPACT_OPS_PANEL_GAP}px)`,
                height: COMPACT_OPS_PANEL_HEIGHT,
                width: Math.max(resolvedWidth, COMPACT_OPS_PANEL_MIN_WIDTH),
              }}
              onClick={(event) => event.stopPropagation()}
            >
              {upstreamImageUrl && (
                <div className="flex shrink-0 items-center px-3 pt-3">
                  <div className="group relative h-9 w-9 overflow-hidden rounded-md border border-white/10">
                    <img
                      src={resolveImageDisplayUrl(upstreamImageUrl)}
                      alt=""
                      className="h-full w-full object-cover"
                      draggable={false}
                    />
                    <button
                      type="button"
                      title="取消引用此素材"
                      className="nodrag absolute right-0 top-0 z-10 hidden h-4 w-4 items-center justify-center rounded-bl-md bg-black/75 text-white transition-colors hover:bg-red-500 group-hover:flex"
                      onMouseDown={(event) => event.stopPropagation()}
                      onClick={(event) => {
                        event.stopPropagation();
                        handleDetachUpstreamImage();
                      }}
                    >
                      <X className="h-3 w-3" strokeWidth={2.5} />
                    </button>
                  </div>
                </div>
              )}
              <textarea
                value={
                  mode === 'imageToPrompt'
                    ? instruction === IMAGE_TO_PROMPT_DEFAULT_CONTENT ? '' : instruction
                    : content
                }
                onChange={(event) => {
                  const field = mode === 'imageToPrompt' ? 'instruction' : 'content';
                  updateNodeData(id, { [field]: event.target.value });
                }}
                onMouseDown={(event) => event.stopPropagation()}
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
                placeholder={mode === 'imageToPrompt' ? IMAGE_TO_PROMPT_DEFAULT_CONTENT : textPlaceholder}
                className={`ui-scrollbar nodrag nowheel min-h-0 w-full flex-1 resize-none border-none bg-transparent px-3 pt-3 text-sm leading-6 text-text-dark outline-none ${CANVAS_NODE_INPUT_PLACEHOLDER_CLASS}`}
              />
              <div className="flex shrink-0 items-center justify-between gap-2 px-3 py-2">
                {/* 文生视频 / 反推提示词的模型不在文本节点上选：文生视频走下游视频节点的
                    model，反推提示词接口压根不收 model。所以这两种模式都不显示模型选择器，
                    只保留右侧提交按钮（占位 span 维持 justify-between 把按钮顶到右边）。 */}
                {mode === 'textToVideo' || mode === 'imageToPrompt' ? (
                  <span />
                ) : (
                  <ProviderModelPicker
                    selectedModelId={modelId}
                    onChange={(nextModelId) => updateNodeData(id, { model: nextModelId })}
                    popoverPlacement="top"
                  />
                )}
                <div className="flex items-center gap-1.5">
                  {mode === 'imageToPrompt' && (
                    <CreditCostInline display={reversePromptCost.data?.data.display} />
                  )}
                  <button
                    type="button"
                    disabled={submitDisabled}
                    title={t('node.textNode.submit')}
                    onClick={(event) => {
                      event.stopPropagation();
                      handleSubmit();
                    }}
                    className={`${NODE_GENERATE_BUTTON_BASE_CLASS} ${
                      submitDisabled
                        ? NODE_GENERATE_BUTTON_DISABLED_CLASS
                        : NODE_GENERATE_BUTTON_ENABLED_CLASS
                    }`}
                  >
                    {isGenerating ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <ArrowUp className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        // 默认视图（writing / textToMusic）：节点本体即文本编辑区——有内容
        // 时直接渲染 markdown，双击进入编辑；空内容时退回到 capability
        // picker（让用户选下一步要做什么 / 切到其它模式）。底部那条原本
        // 的 prompt + send 面板已移除——writing/textToMusic 的 submit
        // 之前就是 stub，留着只会和正文重复编辑同一个 content 字段。
        <div
          className={`flex h-full w-full flex-col rounded-[var(--node-radius)] border transition-colors ${inputBodyToneClass}`}
          onDoubleClick={(event) => {
            if (isEditingContent || isSystemManaged) return;
            event.stopPropagation();
            enterEditMode();
          }}
        >
          {isEditingContent ? (
            <textarea
              ref={editTextareaRef}
              value={content}
              onChange={(event) => updateNodeData(id, {
                content: event.target.value,
                workflowTextGenerated: false,
              })}
              onMouseDown={(event) => event.stopPropagation()}
              onClick={(event) => event.stopPropagation()}
              onKeyDown={(event) => {
                event.stopPropagation();
                if (event.key === 'Escape') {
                  setIsEditingContent(false);
                  editTextareaRef.current?.blur();
                }
              }}
              onBlur={() => setIsEditingContent(false)}
              placeholder={textPlaceholder}
              className={`ui-scrollbar nodrag nowheel h-full w-full resize-none border-none bg-transparent px-4 py-4 text-sm leading-6 text-text-dark outline-none ${CANVAS_NODE_INPUT_PLACEHOLDER_CLASS}`}
            />
          ) : hasUserContent ? (
            <div className="ui-scrollbar nowheel max-h-full w-full flex-1 overflow-y-auto px-4 py-4 text-sm leading-6 text-text-dark">
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkBreaks]}
                components={{
                  h1: ({ ...props }) => <h1 className="mb-1 mt-2 text-base font-semibold" {...props} />,
                  h2: ({ ...props }) => <h2 className="mb-1 mt-2 text-sm font-semibold" {...props} />,
                  h3: ({ ...props }) => <h3 className="mb-1 mt-1 text-sm font-semibold" {...props} />,
                  p: ({ ...props }) => <p className="my-1" {...props} />,
                  strong: ({ ...props }) => <strong className="font-semibold text-text-dark" {...props} />,
                  em: ({ ...props }) => <em className="italic" {...props} />,
                  ul: ({ ...props }) => <ul className="my-1 ml-5 list-disc" {...props} />,
                  ol: ({ ...props }) => <ol className="my-1 ml-5 list-decimal" {...props} />,
                  li: ({ ...props }) => <li className="my-0.5" {...props} />,
                  code: ({ ...props }) => (
                    <code className="rounded bg-white/10 px-1 py-0.5 text-xs" {...props} />
                  ),
                  hr: () => <hr className="my-2 border-white/10" />,
                }}
              >
                {content}
              </ReactMarkdown>
            </div>
          ) : isSystemManaged ? (
            <div className="flex min-h-0 flex-1 items-center justify-center py-4">
              <AlignJustify className="h-12 w-12 stroke-[1.5] text-text-muted/40" />
            </div>
          ) : pickerDismissed ? (
            // 已选过模式的纯文本节点：空内容时显示占位文案、点击进入编辑，不再显示 picker。
            <div
              className={`flex min-h-0 flex-1 cursor-text items-start px-4 py-4 text-sm leading-6 ${CANVAS_NODE_INPUT_PLACEHOLDER_CLASS}`}
              onClick={(event) => {
                event.stopPropagation();
                enterEditMode();
              }}
            >
              {textPlaceholder}
            </div>
          ) : (
            <div
              className="flex min-h-0 flex-1 flex-col justify-center gap-2 py-4"
              style={{ marginInline: PICKER_INSET }}
            >
              <div className="text-xs text-[var(--canvas-node-input-helper)]">{t('node.textNode.tryHint')}</div>
              <div className="flex flex-col gap-0.5">
                {MODES.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.key}
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        handlePickMode(item.key);
                      }}
                      className="-mx-2 inline-flex items-center gap-3 rounded-lg px-2 py-2 text-sm text-text-dark transition-colors hover:bg-white/[0.08]"
                    >
                      <Icon className="h-4 w-4 text-text-muted/90" />
                      <span>{t(item.labelKey)}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
});

TextAnnotationNode.displayName = 'TextAnnotationNode';

interface WritingOpsPanelProps {
  nodeId: string;
  content: string;
  isGenerating: boolean;
  width: number;
}

function WritingOpsPanel({
  nodeId,
  content,
  isGenerating,
  width,
}: WritingOpsPanelProps) {
  const { t } = useTranslation();
  const updateNodeData = useCanvasStore((state) => state.updateNodeData);
  const [isTranslating, setIsTranslating] = useState(false);
  const textPlaceholder = t('node.textNode.placeholder');

  const handleTranslate = useCallback(async () => {
    if (isGenerating || isTranslating) return;
    const trimmed = content.trim();
    if (trimmed.length === 0) return;
    const project = readUrl().project;
    if (!project) {
      console.error('[text-node] translate: no project in URL');
      return;
    }
    setIsTranslating(true);
    try {
      const translated = await translateNodeText(project, {
        text: content,
        nodeId,
        nodeType: 'text',
      });
      updateNodeData(nodeId, { content: translated });
    } catch (error) {
      console.error('[text-node] translate failed', error);
    } finally {
      setIsTranslating(false);
    }
  }, [content, isGenerating, isTranslating, nodeId, updateNodeData]);

  const translateDisabled = isGenerating || isTranslating || content.trim().length === 0;

  return (
    <div
      className={`nodrag absolute left-1/2 z-[300] flex -translate-x-1/2 flex-col rounded-[var(--node-radius)] border ${CANVAS_NODE_INPUT_SURFACE_CLASS} ${CANVAS_NODE_INPUT_FRAME_CLASS}`}
      style={{
        top: `calc(100% + ${COMPACT_OPS_PANEL_GAP}px)`,
        height: COMPACT_OPS_PANEL_HEIGHT,
        width: Math.max(width, COMPACT_OPS_PANEL_MIN_WIDTH),
      }}
      onClick={(event) => event.stopPropagation()}
    >
      <textarea
        value={content}
        onChange={(event) => updateNodeData(nodeId, { content: event.target.value })}
        onMouseDown={(event) => event.stopPropagation()}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => event.stopPropagation()}
        placeholder={textPlaceholder}
        className={`ui-scrollbar nodrag nowheel min-h-0 w-full flex-1 resize-none border-none bg-transparent px-3 pt-3 text-sm leading-6 text-text-dark outline-none ${CANVAS_NODE_INPUT_PLACEHOLDER_CLASS}`}
        disabled={isGenerating}
      />
      <div className="flex shrink-0 items-center justify-end gap-1 px-3 py-2">
        <button
          type="button"
          title={t('node.textNode.translate')}
          onClick={(event) => {
            event.stopPropagation();
            void handleTranslate();
          }}
          disabled={translateDisabled}
          className={`${NODE_INLINE_ICON_BUTTON_CLASS} ${
            isTranslating ? NODE_INLINE_ICON_BUTTON_ACTIVE_CLASS : ''
          }`}
        >
          {isTranslating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Languages className="h-4 w-4" />
          )}
        </button>
      </div>
    </div>
  );
}
