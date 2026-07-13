// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { memo, useCallback, useMemo, useRef, useState } from 'react';
import { NodeToolbar as ReactFlowNodeToolbar, Position, useViewport } from '@xyflow/react';
import ReactCrop, { type Crop, type PixelCrop } from 'react-image-crop';
import 'react-image-crop/dist/ReactCrop.css';
import { ArrowLeft, Loader2, UserRound } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  DEFAULT_NODE_WIDTH,
  type CanvasNode,
} from '@/features/canvas/domain/canvasNodes';
import {
  centerInitialCrop,
  exportCroppedBlob,
  pixelCropFromPercentCrop,
} from './BackgroundCropperDialog';
import { uploadFreezoneImage } from '@/api/ops';
import { resolveImageDisplayUrl } from '@/features/canvas/application/imageData';
import { readUrl } from '@/lib/url-params';
import { NODE_TOOLBAR_CLASS } from './nodeToolbarConfig';
import { CANVAS_NODE_TOOLBAR_PILL_CLASS } from './nodeFrameStyles';

/** 比例选项：original 表示原图比例。 */
const ASPECT_OPTIONS = ['original', '1:1', '4:3', '3:4', '16:9', '9:16'] as const;
type AspectOption = (typeof ASPECT_OPTIONS)[number];

function parseAspect(option: AspectOption, natural: { w: number; h: number } | null): number {
  if (option === 'original') {
    return natural && natural.h > 0 ? natural.w / natural.h : 1;
  }
  const [w, h] = option.split(':').map(Number);
  return w > 0 && h > 0 ? w / h : 1;
}

interface EmotionCropOverlayProps {
  node: CanvasNode;
  imageSource: string;
  onCancel: () => void;
  /** 框选确认：裁剪区域已上传，返回后端静态地址。 */
  onConfirm: (croppedUrl: string) => void;
}

/**
 * 情绪调节第一步：在源图片节点上手动框选人物区域（libtv 同款交互）。
 * 框选层直接叠在节点图片上（随缩放对齐），顶部工具栏提供比例选择和确认；
 * 确认后把选区按原图分辨率裁剪、上传，产出角色参考图。
 */
export const EmotionCropOverlay = memo(
  ({ node, imageSource, onCancel, onConfirm }: EmotionCropOverlayProps) => {
    const { t } = useTranslation();
    const { zoom } = useViewport();
    const imgRef = useRef<HTMLImageElement | null>(null);
    const [crop, setCrop] = useState<Crop | undefined>(undefined);
    const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
    const [aspectOption, setAspectOption] = useState<AspectOption>('original');
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // 节点在画布坐标系里的尺寸（flow 单位）。
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

    // 节点用 object-contain 显示图片：算出图片实际显示矩形并乘以 zoom，
    // 框选层只覆盖这块，任意缩放下都与节点上的图对齐。
    const display = useMemo(() => {
      if (!natural) {
        return { width: nodeWidth * zoom, height: nodeHeight * zoom };
      }
      const fit = Math.min(nodeWidth / natural.w, nodeHeight / natural.h);
      return { width: natural.w * fit * zoom, height: natural.h * fit * zoom };
    }, [natural, nodeHeight, nodeWidth, zoom]);

    const aspectValue = useMemo(
      () => parseAspect(aspectOption, natural),
      [aspectOption, natural],
    );

    const handleImageLoad = useCallback(
      (event: React.SyntheticEvent<HTMLImageElement>) => {
        const img = event.currentTarget;
        imgRef.current = img;
        setNatural({ w: img.naturalWidth, h: img.naturalHeight });
        const ratio =
          img.naturalHeight > 0 ? img.naturalWidth / img.naturalHeight : 1;
        // 初始框选：略小于全图的居中区域，按当前比例锁定。
        setCrop(centerInitialCrop(img.width, img.height, ratio));
      },
      [],
    );

    const handleAspectChange = useCallback(
      (option: AspectOption) => {
        setAspectOption(option);
        const img = imgRef.current;
        if (!img) return;
        setCrop(centerInitialCrop(img.width, img.height, parseAspect(option, natural)));
      },
      [natural],
    );

    const handleConfirm = useCallback(async () => {
      const img = imgRef.current;
      if (!img || !crop || uploading) return;
      const project = readUrl().project;
      if (!project) {
        setError('no project in URL');
        return;
      }
      const pixelCrop: PixelCrop = pixelCropFromPercentCrop(crop, img.width, img.height);
      if (pixelCrop.width < 4 || pixelCrop.height < 4) return;
      setUploading(true);
      setError(null);
      try {
        const blob = await exportCroppedBlob(img, pixelCrop);
        const uploaded = await uploadFreezoneImage(
          project,
          blob,
          `emotion-ref-${Date.now()}.png`,
        );
        onConfirm(uploaded.url.split('?')[0]);
      } catch (err) {
        console.error('[emotion-crop] crop upload failed', err);
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setUploading(false);
      }
    }, [crop, onConfirm, uploading]);

    const displaySrc = resolveImageDisplayUrl(imageSource);

    return (
      <>
        {/* 框选层：覆盖节点上显示的图片（随缩放对齐）。 */}
        <ReactFlowNodeToolbar
          nodeId={node.id}
          isVisible
          position={Position.Top}
          align="center"
          offset={0}
          className={NODE_TOOLBAR_CLASS}
        >
          <div className="relative" style={{ width: 0, height: 0 }}>
            <div
              className="absolute overflow-hidden rounded-[var(--node-radius)]"
              style={{
                width: display.width,
                height: display.height,
                left: '50%',
                top: (nodeHeight * zoom) / 2,
                transform: 'translate(-50%, -50%)',
              }}
              onClick={(event) => event.stopPropagation()}
            >
              <ReactCrop
                className="h-full w-full [&_img]:h-full [&_img]:w-full [&_.ReactCrop__crop-selection]:!border-2 [&_.ReactCrop__crop-selection]:!border-white [&_.ReactCrop__crop-selection]:shadow-[0_0_0_9999px_rgba(0,0,0,0.45)]"
                crop={crop}
                onChange={(_, percentCrop) => setCrop(percentCrop)}
                aspect={aspectValue}
                keepSelection
                ruleOfThirds
              >
                <img
                  src={displaySrc}
                  alt=""
                  onLoad={handleImageLoad}
                  style={{ width: display.width, height: display.height, objectFit: 'fill' }}
                  draggable={false}
                />
              </ReactCrop>
            </div>
          </div>
        </ReactFlowNodeToolbar>

        {/* 顶部框选工具栏：返回 | 提示 | 比例 | 确认。 */}
        <ReactFlowNodeToolbar
          nodeId={node.id}
          isVisible
          position={Position.Top}
          align="center"
          offset={16}
          className={NODE_TOOLBAR_CLASS}
        >
          <div
            className={`flex items-center gap-2 ${CANVAS_NODE_TOOLBAR_PILL_CLASS}`}
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-text-muted transition-colors hover:bg-white/[0.08] hover:text-text-dark"
              onClick={onCancel}
              title={t('common.cancel')}
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <span className="flex items-center gap-1.5 text-xs text-text-dark/86">
              <UserRound className="h-3.5 w-3.5 text-text-muted" />
              {t('portraitTexture.cropHint')}
            </span>
            <select
              value={aspectOption}
              onChange={(event) => handleAspectChange(event.target.value as AspectOption)}
              className="nodrag h-7 rounded-md border border-white/12 bg-transparent px-1.5 text-xs text-text-dark focus:outline-none"
            >
              {ASPECT_OPTIONS.map((option) => (
                <option key={option} value={option} className="bg-[#282828]">
                  {option === 'original' ? t('portraitTexture.originalAspect') : option}
                </option>
              ))}
            </select>
            {error && (
              <span className="max-w-[160px] truncate text-xs text-red-300" title={error}>
                {error}
              </span>
            )}
            <button
              type="button"
              className="flex h-8 shrink-0 items-center justify-center gap-1 rounded-full bg-white px-3.5 text-xs font-medium text-bg-dark transition-colors hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-55"
              onClick={() => void handleConfirm()}
              disabled={uploading || !crop}
            >
              {uploading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {t('portraitTexture.cropConfirm')}
            </button>
          </div>
        </ReactFlowNodeToolbar>
      </>
    );
  },
);

EmotionCropOverlay.displayName = 'EmotionCropOverlay';
