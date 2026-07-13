// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { memo, useCallback, useMemo, useState } from 'react';
import { NodeToolbar as ReactFlowNodeToolbar, Position } from '@xyflow/react';
import { ArrowUp, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  CANVAS_NODE_TYPES,
  DEFAULT_ASPECT_RATIO,
  EXPORT_RESULT_NODE_DEFAULT_WIDTH,
  EXPORT_RESULT_NODE_LAYOUT_HEIGHT,
  type CanvasNode,
} from '@/features/canvas/domain/canvasNodes';
import {
  DEFAULT_EMOTION_KEY,
  EMOTION_GRID,
  EMOTION_GRID_SIZE,
  emotionEntryAt,
  emotionSampleImageUrl,
  findEmotionEntry,
} from '@/features/canvas/domain/emotionAdjust';
import { useCanvasStore } from '@/stores/canvasStore';
import {
  fetchFreezoneJobResult,
  submitFreezonePortraitTexture,
} from '@/api/ops';
import { CreditCostInline } from '@/components/credit-cost-inline';
import { awaitTaskCompletion } from '@/api/tasks';
import { generationTaskDescriptor } from '@/features/canvas/application/resumeGeneration';
import { inheritMainlineFields } from '@/features/canvas/domain/inheritMainlineFields';
import { useFreezoneImageModels } from '@/features/canvas/hooks/useFreezoneImageModels';
import { useGenerationCreditCost } from '@/lib/queries/generation-credit-cost';
import { readUrl } from '@/lib/url-params';
import { NODE_TOOLBAR_CLASS } from './nodeToolbarConfig';
import { NODE_FLOATING_PANEL_SURFACE_CLASS } from './nodeControlStyles';
import { ZoomScaledToolbar } from './ZoomScaledToolbar';

const IMAGE_SIZE_OPTIONS = ['1K', '2K', '4K'] as const;

function imageModelSupportsQuality(apiModel: string | null | undefined): boolean {
  const normalized = String(apiModel ?? '').trim().toLowerCase();
  return (
    normalized === 'gpt-image-2'
    || normalized === 'image-2'
    || normalized === 'image-2-official'
    || normalized.includes('gpt-image')
  );
}

/** 把 public 静态资源取成 dataURL；404 或跨域失败时返回 null（跳过样例参考图）。 */
async function fetchAsDataUrl(url: string): Promise<string | null> {
  try {
    const response = await fetch(url);
    if (!response.ok) return null;
    const blob = await response.blob();
    if (!blob.type.startsWith('image/')) return null;
    return await new Promise<string | null>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : null);
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
}

interface EmotionEditorOverlayProps {
  /** 源图片节点（编辑器锚定在它下方，结果节点也挂在它下游）。 */
  node: CanvasNode;
  /** 框选并上传后的人物参考图静态地址。 */
  croppedImageUrl: string;
  onClose: () => void;
}

export const EmotionEditorOverlay = memo(
  ({ node, croppedImageUrl, onClose }: EmotionEditorOverlayProps) => {
    const { t, i18n } = useTranslation();
    const isZh = Boolean(i18n.language?.startsWith('zh'));
    const addNode = useCanvasStore((state) => state.addNode);
    const addEdge = useCanvasStore((state) => state.addEdge);
    const setSelectedNode = useCanvasStore((state) => state.setSelectedNode);
    const findNodePosition = useCanvasStore((state) => state.findNodePosition);
    const updateNodeData = useCanvasStore((state) => state.updateNodeData);

    const [emotionKey, setEmotionKey] = useState(DEFAULT_EMOTION_KEY);
    const [imageSize, setImageSize] = useState<(typeof IMAGE_SIZE_OPTIONS)[number]>('2K');
    const [sampleBroken, setSampleBroken] = useState(false);

    const selectedEmotion = useMemo(
      () => findEmotionEntry(emotionKey) ?? EMOTION_GRID[0],
      [emotionKey],
    );

    const { models: imageModels } = useFreezoneImageModels();
    const selectedModel = imageModels[0];
    const creditCost = useGenerationCreditCost(
      'image_selection',
      selectedModel?.apiModel ?? null,
      {
        surface: 'canvas',
        params: imageModelSupportsQuality(selectedModel?.apiModel)
          ? { size: imageSize, quality: 'medium' }
          : { size: imageSize },
      },
    );

    const handleSelectEmotion = useCallback((key: string) => {
      setEmotionKey(key);
      setSampleBroken(false);
    }, []);

    const handleSubmit = useCallback(async () => {
      const project = readUrl().project;
      if (!project) {
        console.error('[emotion-adjust] no project in URL — cannot submit');
        return;
      }

      const sourceAspectRatio =
        typeof (node.data as { aspectRatio?: unknown }).aspectRatio === 'string'
          ? ((node.data as { aspectRatio?: string }).aspectRatio ?? DEFAULT_ASPECT_RATIO)
          : DEFAULT_ASPECT_RATIO;
      const position = findNodePosition(
        node.id,
        EXPORT_RESULT_NODE_DEFAULT_WIDTH,
        EXPORT_RESULT_NODE_LAYOUT_HEIGHT,
      );
      const generationStartedAt = Date.now();
      const displayName = `${t('portraitTexture.emotionAdjust')} · ${
        isZh ? selectedEmotion.label : selectedEmotion.labelEn
      }`;
      const initialData = inheritMainlineFields(
        { data: node.data as Record<string, unknown> },
        {
          displayName,
          imageUrl: null,
          previewImageUrl: null,
          aspectRatio: sourceAspectRatio,
          resultKind: 'generic',
          isGenerating: true,
          generationStartedAt,
          generationDurationMs: 60000,
        },
      );
      const nextNodeId = addNode(
        CANVAS_NODE_TYPES.exportImage,
        position,
        initialData as unknown as Parameters<typeof addNode>[2],
      );
      addEdge(node.id, nextNodeId);
      setSelectedNode(nextNodeId);
      onClose();

      try {
        // 样例图就绪时作为表情参考一并提交（fetch 失败/未放图则只用文字提示词）。
        const expressionReferenceUrl = sampleBroken
          ? null
          : await fetchAsDataUrl(emotionSampleImageUrl(selectedEmotion.key));
        const emotionText = isZh
          ? `${selectedEmotion.label}（${selectedEmotion.promptZh}）`
          : `${selectedEmotion.labelEn} (${selectedEmotion.promptEn})`;
        const ref = await submitFreezonePortraitTexture(project, {
          sourceUrl: croppedImageUrl.split('?')[0],
          mode: 'emotion_adjust',
          emotion: emotionText,
          expressionReferenceUrl,
          imageSize,
        });
        updateNodeData(nextNodeId, generationTaskDescriptor(ref));
        const completed = await awaitTaskCompletion(ref.task_key, project);
        const directUrl = completed.result?.['output_url'] as string | undefined;
        let url = directUrl;
        if (!url) {
          const fallback = await fetchFreezoneJobResult(project, ref.task_type, ref.job_id);
          url = fallback.url;
        }
        updateNodeData(nextNodeId, {
          imageUrl: url,
          previewImageUrl: url,
          isGenerating: false,
          generationStartedAt: null,
          generationError: null,
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error('[emotion-adjust] generation failed', err);
        updateNodeData(nextNodeId, {
          isGenerating: false,
          generationStartedAt: null,
          generationError: message,
        });
      }
    }, [
      addEdge,
      addNode,
      croppedImageUrl,
      findNodePosition,
      imageSize,
      isZh,
      node,
      onClose,
      sampleBroken,
      selectedEmotion,
      setSelectedNode,
      t,
      updateNodeData,
    ]);

    return (
      <ReactFlowNodeToolbar
        nodeId={node.id}
        isVisible
        position={Position.Bottom}
        align="start"
        offset={16}
        className={NODE_TOOLBAR_CLASS}
      >
        <ZoomScaledToolbar origin="top left">
          <div
            className={`flex w-[560px] flex-col gap-3 p-3.5 ${NODE_FLOATING_PANEL_SURFACE_CLASS}`}
            onClick={(event) => event.stopPropagation()}
          >
            {/* 头部：关闭 | 标题 | 尺寸 | 积分 | 提交 */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-text-muted transition-colors hover:bg-white/[0.08] hover:text-text-dark"
                onClick={onClose}
                title={t('portraitTexture.clear')}
              >
                <X className="h-4 w-4" />
              </button>
              <span className="h-4 w-px bg-white/12" />
              <span className="flex-1 truncate text-sm font-medium text-text-dark">
                {t('portraitTexture.emotionAdjust')}
              </span>
              <select
                value={imageSize}
                onChange={(event) =>
                  setImageSize(event.target.value as (typeof IMAGE_SIZE_OPTIONS)[number])
                }
                className="nodrag h-7 rounded-md border border-white/12 bg-transparent px-1.5 text-xs text-text-dark focus:outline-none"
              >
                {IMAGE_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size} className="bg-[#282828]">
                    {size}
                  </option>
                ))}
              </select>
              <CreditCostInline display={creditCost.data?.data.display} />
              <button
                type="button"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-bg-dark transition-colors hover:bg-white/90"
                onClick={() => void handleSubmit()}
                title={t('portraitTexture.emotionSubmit')}
              >
                <ArrowUp className="h-4 w-4" />
              </button>
            </div>

            {/* 人物参考 chip（框选结果缩略图） */}
            <div className="flex items-center gap-2">
              <span className="inline-flex h-7 items-center gap-1.5 rounded-full bg-white/[0.09] pl-1 pr-2.5 text-xs font-medium text-white">
                <img
                  src={croppedImageUrl}
                  alt=""
                  className="h-5 w-5 rounded-full object-cover"
                  draggable={false}
                />
                {t('portraitTexture.characterRef')}
              </span>
            </div>

            <div className="flex gap-3">
              {/* 左：表情样例图 + 情绪定位 */}
              <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl bg-white/[0.04]">
                <div className="relative aspect-[4/3] w-full overflow-hidden">
                  {sampleBroken ? (
                    <div className="flex h-full w-full items-center justify-center bg-white/[0.05] px-4 text-center text-xs leading-5 text-text-muted">
                      {t('portraitTexture.samplePlaceholder')}
                    </div>
                  ) : (
                    <img
                      key={selectedEmotion.key}
                      src={emotionSampleImageUrl(selectedEmotion.key)}
                      alt={isZh ? selectedEmotion.label : selectedEmotion.labelEn}
                      className="h-full w-full object-cover"
                      draggable={false}
                      onError={() => setSampleBroken(true)}
                    />
                  )}
                </div>
                <div className="flex items-center gap-2 px-3 py-2 text-xs">
                  <span className="shrink-0 text-text-muted">
                    {t('portraitTexture.emotionAnchor')}
                  </span>
                  <span className="truncate font-medium text-text-dark">
                    {isZh ? selectedEmotion.label : selectedEmotion.labelEn}
                  </span>
                </div>
              </div>

              {/* 右：5×5 情绪网格（上激动/下平静/左亲近/右疏离） */}
              <div className="relative flex w-[240px] shrink-0 flex-col items-center justify-center rounded-xl bg-white/[0.04] px-7 py-6">
                <span className="absolute top-2 left-1/2 -translate-x-1/2 text-[11px] text-text-muted">
                  {t('portraitTexture.axisExcited')}
                </span>
                <span className="absolute bottom-2 left-1/2 -translate-x-1/2 text-[11px] text-text-muted">
                  {t('portraitTexture.axisCalm')}
                </span>
                <span className="absolute left-2 top-1/2 -translate-y-1/2 text-[11px] text-text-muted [writing-mode:vertical-rl]">
                  {t('portraitTexture.axisClose')}
                </span>
                <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-text-muted [writing-mode:vertical-rl]">
                  {t('portraitTexture.axisDistant')}
                </span>
                <div
                  className="grid gap-3"
                  style={{ gridTemplateColumns: `repeat(${EMOTION_GRID_SIZE}, minmax(0, 1fr))` }}
                >
                  {Array.from({ length: EMOTION_GRID_SIZE }, (_, row) =>
                    Array.from({ length: EMOTION_GRID_SIZE }, (_, col) => {
                      const entry = emotionEntryAt(row, col);
                      if (!entry) return <span key={`${row}-${col}`} className="h-6 w-6" />;
                      const isSelected = entry.key === selectedEmotion.key;
                      return (
                        <button
                          key={entry.key}
                          type="button"
                          title={isZh ? entry.label : entry.labelEn}
                          onClick={() => handleSelectEmotion(entry.key)}
                          className="flex h-6 w-6 items-center justify-center"
                        >
                          <span
                            className={
                              isSelected
                                ? 'h-4 w-4 rounded-full bg-white shadow-[0_0_10px_rgba(255,255,255,0.55)] transition-all'
                                : 'h-2 w-2 rounded-full bg-white/38 transition-all hover:h-3 hover:w-3 hover:bg-white/75'
                            }
                          />
                        </button>
                      );
                    }),
                  )}
                </div>
              </div>
            </div>
          </div>
        </ZoomScaledToolbar>
      </ReactFlowNodeToolbar>
    );
  },
);

EmotionEditorOverlay.displayName = 'EmotionEditorOverlay';
