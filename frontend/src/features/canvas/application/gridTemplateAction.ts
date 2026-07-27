// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import {
  fetchFreezoneJobResult,
  submitFreezoneTemplateEdit,
  type FreezoneTemplateEditMode,
} from '@/api/ops';
import { awaitTaskCompletion } from '@/api/tasks';
import {
  CANVAS_NODE_TYPES,
  DEFAULT_ASPECT_RATIO,
  EXPORT_RESULT_NODE_DEFAULT_WIDTH,
  EXPORT_RESULT_NODE_LAYOUT_HEIGHT,
} from '@/features/canvas/domain/canvasNodes';
import { readUrl } from '@/lib/url-params';
import { useCanvasStore } from '@/stores/canvasStore';

import { generationTaskDescriptor } from './resumeGeneration';

/** 宫格模板动作 key（原 GridActionConfirmOverlay 私有，抽到 application 供两处共用）。 */
export type GridActionKey =
  | 'multiCameraGrid'
  | 'plotFourGrid'
  | 'faceThreeView'
  | 'productThreeView'
  | 'serialStoryboard25'
  | 'cinematicLightCorrection'
  | 'characterThreeView'
  | 'sceneSettingSheet'
  | 'frameProjection3sLater'
  | 'frameProjection5sEarlier';

export const GRID_ACTION_MODE_MAP: Record<GridActionKey, FreezoneTemplateEditMode> = {
  multiCameraGrid: 'multi_camera_nine_grid',
  plotFourGrid: 'story_pitch_four_grid',
  faceThreeView: 'character_face_three_view',
  productThreeView: 'product_three_view',
  serialStoryboard25: 'storyboard_25_grid',
  cinematicLightCorrection: 'cinematic_light_correction',
  characterThreeView: 'character_three_view_generation',
  sceneSettingSheet: 'scene_setting_sheet',
  frameProjection3sLater: 'image_projection_after_3s',
  frameProjection5sEarlier: 'image_projection_before_5s',
};

/**
 * 宫格模板提交编排（从 GridActionConfirmOverlay.handleSubmit 原样搬出，语义零变化）：
 * 同步在源节点下游建 isGenerating 的 exportImage 结果节点并连边/选中（首个 await 之前，
 * 调用方随后关 UI 不影响时序），然后提交 /freezone/template-edit → 等任务完成 →
 * 把产物 url 回填；失败把错误写到结果节点。
 *
 * @returns 新建结果节点 id；缺 project 或源节点已不存在时返回 null。
 */
export async function submitGridTemplateAction(params: {
  sourceNodeId: string;
  imageSource: string;
  key: GridActionKey;
  label: string;
}): Promise<string | null> {
  const project = readUrl().project;
  if (!project) {
    console.error('[grid-action] no project in URL — cannot submit');
    return null;
  }
  const store = useCanvasStore.getState();
  const node = store.nodes.find((candidate) => candidate.id === params.sourceNodeId);
  if (!node) {
    return null;
  }

  const sourceAspectRatio =
    typeof (node.data as { aspectRatio?: unknown }).aspectRatio === 'string'
      ? ((node.data as { aspectRatio?: string }).aspectRatio ?? DEFAULT_ASPECT_RATIO)
      : DEFAULT_ASPECT_RATIO;
  const position = store.findNodePosition(
    node.id,
    EXPORT_RESULT_NODE_DEFAULT_WIDTH,
    EXPORT_RESULT_NODE_LAYOUT_HEIGHT,
  );
  const generationStartedAt = Date.now();
  const nextNodeId = store.addNode(CANVAS_NODE_TYPES.exportImage, position, {
    displayName: params.label,
    imageUrl: null,
    previewImageUrl: null,
    aspectRatio: sourceAspectRatio,
    resultKind: 'generic',
    isGenerating: true,
    generationStartedAt,
  });
  store.addEdge(node.id, nextNodeId);
  store.setSelectedNode(nextNodeId);

  try {
    const ref = await submitFreezoneTemplateEdit(project, {
      sourceUrl: params.imageSource.split('?')[0],
      mode: GRID_ACTION_MODE_MAP[params.key],
      prompt: params.label,
    });
    useCanvasStore.getState().updateNodeData(nextNodeId, generationTaskDescriptor(ref));
    const completed = await awaitTaskCompletion(ref.task_key, project);
    const directUrl = completed.result?.['output_url'] as string | undefined;
    let url = directUrl;
    if (!url) {
      const fallback = await fetchFreezoneJobResult(project, ref.task_type, ref.job_id);
      url = fallback.url;
    }
    useCanvasStore.getState().updateNodeData(nextNodeId, {
      imageUrl: url,
      previewImageUrl: url,
      isGenerating: false,
      generationStartedAt: null,
      generationError: null,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error('[grid-action] generation failed', err);
    useCanvasStore.getState().updateNodeData(nextNodeId, {
      isGenerating: false,
      generationStartedAt: null,
      generationError: message,
    });
  }
  return nextNodeId;
}
