// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useCallback, useState, type ReactElement } from 'react';
import { X } from 'lucide-react';

import { ImageGenerationForm } from '@/features/canvas/nodes/shared/ImageGenerationForm';
import { useImageGenerationForm } from '@/features/canvas/nodes/shared/useImageGenerationForm';
import { spawnAssetLibraryReferences } from '@/features/canvas/nodes/shared/assetLibraryReferenceSpawn';
import { resolveImageDisplayUrl } from '@/features/canvas/application/imageData';
import {
  ASSET_BOARD_IMAGE_OP_MAP,
  isAssetBoardImageOpKey,
  isGridImageOpKey,
  runAssetBoardImageOp,
} from '@/features/canvas/application/assetBoardImageOps';
import { useFreezoneImageModels } from '@/features/canvas/hooks/useFreezoneImageModels';
import { imageModelSupportsQuality } from '@/features/canvas/ui/GridActionConfirmOverlay';
import { useGenerationCreditCost } from '@/lib/queries/generation-credit-cost';
import {
  AssetLibraryModal,
  type AssetLibrarySelection,
} from '@/features/canvas/ui/AssetLibraryModal';
import { CANVAS_NODE_OPS_PANEL_CLASS } from '@/features/canvas/ui/nodeFrameStyles';
import {
  NODE_REFERENCE_MEDIA_CHIP_CLASS,
  NODE_REFERENCE_MEDIA_DETACH_CLASS,
} from '@/features/canvas/ui/nodeControlStyles';
import { useCanvasStore } from '@/stores/canvasStore';
import { readUrl } from '@/lib/url-params';

import { AssetBoardImageOpChip } from './AssetBoardImageOpChip';
import { AssetBoardReferenceDropZone } from './AssetBoardReferenceDropZone';

/**
 * 表单在详情里的固定高度。从 248 收到 184（用户要求）：详情现在是「媒体撑满 +
 * 生成条钉底」，表单占多高就等于上方内容区少多高；184 仍留得下 4~5 行提示词。
 */
const FORM_HEIGHT_PX = 184;

/**
 * 带功能 chip 时的表单高度：chip 行 + 说明行大约占 56px，不加高就会把提示词区
 * 压到 2 行以内。
 */
const FORM_HEIGHT_WITH_OP_PX = 240;

/**
 * 故事板详情里的图片生成条：媒体区下方挂 `ImageGenerationForm`，让**空节点**能
 * 从零出图、已有产物的节点能改参数重生成（与工作流走同一个 `useImageGenerationForm`，
 * 因此参数/提示词/参考图三边共用节点 data，两个视图天然同步）。
 *
 * 两个宿主浮层 props 的落地：
 * - `onStylePickerOpenChange`：工作流用它临时藏起叠在面板下方的「生成历史」条；
 *   详情面板没有那条历史，故 no-op。
 * - `onOpenAssetLibrary`：接真弹窗。选中的图会在画布上生成 upload 参考节点并连线
 *   到本节点（编排与工作流共用 `spawnAssetLibraryReferences`），回流后表现为表单
 *   chips 行里的参考图——不是一个点了没反应的按钮。
 *
 * 自带参考图（`data.referenceImageUrl`，资产库/替换素材直接选到、无上游连线的那张）
 * 共用表单 `ImageGenerationForm` 不显示（它只渲上游连线引用 chip）。故事板详情的底部
 * 「参考素材」只读行有生成表单时被收掉（避免与表单 chip 重复），若不在此补显示，自带
 * 参考图就会从详情里消失——所以这里在表单顶部补一枚自带参考 chip（与上游 chip 紧邻、
 * 同款样式），只在宿主渲染、共用表单零改动。 */
export function AssetBoardImageGenForm({ nodeId }: { nodeId: string }): ReactElement {
  const { formProps, isGenerating, referenceImageUrl } = useImageGenerationForm(nodeId);
  const updateNodeData = useCanvasStore((state) => state.updateNodeData);
  const [isAssetLibraryOpen, setIsAssetLibraryOpen] = useState(false);

  // 功能节点（详情工具条点了某个一图流功能后建出来的那种）：输入框里、提示词
  // 正上方多一枚可关可切的功能 chip，↑ 走对应能力而不是常规文生图。普通图片生成
  // 节点没有这个字段，下面所有分支都退化成原来的行为。
  const opKeyRaw = useCanvasStore((state) => {
    const node = state.nodes.find((candidate) => candidate.id === nodeId);
    return (node?.data as { imageOpKey?: unknown } | undefined)?.imageOpKey;
  });
  const opKey = isAssetBoardImageOpKey(opKeyRaw) ? opKeyRaw : null;

  const noopStylePickerOpenChange = useCallback(() => {}, []);
  // 功能提交不要求提示词（模板本身就是「基于当前图像生成」，提示词是可选补充），
  // 所以不能沿用共用表单那条 `submitDisabled = isGenerating || !hasEffectivePrompt`。
  const handleOpSubmit = useCallback(() => {
    void runAssetBoardImageOp(nodeId);
  }, [nodeId]);

  // 功能节点的算力：宫格按 image_selection 询价（与详情工具条那个下拉同一套查询，
  // 两处显示同一个数）；询价没回来退回功能表里的硬编码 cost。全景/多角度/打光
  // 没有对应口径，返回 null → CreditCostPill 自己不渲染。
  const isGridOp = opKey !== null && isGridImageOpKey(opKey);
  const { models: imageModels } = useFreezoneImageModels();
  const opSelectedModel = imageModels[0];
  // value 传 null 时 useGenerationCreditCost 自己 enabled:false（image_selection
  // 属于 requiresValue 那档），非宫格功能不会白发一次询价请求。
  const opCreditCost = useGenerationCreditCost(
    'image_selection',
    isGridOp ? (opSelectedModel?.apiModel ?? null) : null,
    {
      surface: 'canvas',
      params: imageModelSupportsQuality(opSelectedModel?.apiModel)
        ? { size: '2K', quality: 'medium' }
        : { size: '2K' },
    },
  );
  const opCreditDisplay =
    opKey && isGridOp
      ? (opCreditCost.data?.data.display ?? String(ASSET_BOARD_IMAGE_OP_MAP[opKey].cost))
      : null;
  const handleAssetLibraryConfirm = useCallback(
    (selections: ReadonlyArray<AssetLibrarySelection>) => {
      spawnAssetLibraryReferences(nodeId, selections);
    },
    [nodeId],
  );

  return (
    <div className="flex w-full flex-col">
      {/* 参考区放置层：从左列表把节点卡片拖进来 → addEdge 接成当前节点的上游引用，
          回流后经表单既有 upstream 派生显示为参考缩略图 chip（工作流零改动）。 */}
      <AssetBoardReferenceDropZone nodeId={nodeId}>
        <div
          className={`flex w-full flex-col rounded-[var(--node-radius)] ${CANVAS_NODE_OPS_PANEL_CLASS}`}
          style={{ height: opKey ? FORM_HEIGHT_WITH_OP_PX : FORM_HEIGHT_PX }}
        >
          {/* 自带参考图 chip（共用表单不渲这张）：紧贴表单 chip 行上方补显示，移除
              按钮清空 data.referenceImageUrl（与工作流 ImageGenNode 的「移除参考图」
              同一 patch）。仅在存在自带参考图时出现。 */}
          {referenceImageUrl && (
            <div className="flex shrink-0 items-center gap-1.5 pl-3 pt-3">
              <div className={NODE_REFERENCE_MEDIA_CHIP_CLASS} title="节点自带参考图">
                <img
                  src={resolveImageDisplayUrl(referenceImageUrl)}
                  alt="参考图"
                  className="h-full w-full object-cover"
                  draggable={false}
                />
                <button
                  type="button"
                  title="移除参考图"
                  className={NODE_REFERENCE_MEDIA_DETACH_CLASS}
                  onClick={() => updateNodeData(nodeId, { referenceImageUrl: null })}
                >
                  <X className="h-3 w-3" strokeWidth={2.5} />
                </button>
              </div>
            </div>
          )}
          {/* 功能 chip 挂在输入框内、提示词上方（对标 liblib）：走共用表单新开的
              `promptLeadingSlot` 插槽，表单只认位置不解释内容；工作流的 ImageGenNode
              不传这个 prop，渲染与从前一致。 */}
          <ImageGenerationForm
            {...formProps}
            compact
            onStylePickerOpenChange={noopStylePickerOpenChange}
            onOpenAssetLibrary={() => setIsAssetLibraryOpen(true)}
            promptLeadingSlot={
              opKey ? (
                <AssetBoardImageOpChip nodeId={nodeId} opKey={opKey} disabled={isGenerating} />
              ) : null
            }
            {...(opKey
              ? {
                  onSubmit: handleOpSubmit,
                  submitDisabled: isGenerating,
                  totalCreditCostDisplay: opCreditDisplay,
                }
              : {})}
          />
        </div>
      </AssetBoardReferenceDropZone>
      <AssetLibraryModal
        open={isAssetLibraryOpen}
        project={readUrl().project ?? null}
        allowedMedia={['image']}
        onClose={() => setIsAssetLibraryOpen(false)}
        onConfirm={handleAssetLibraryConfirm}
      />
    </div>
  );
}
