// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CANVAS_NODE_TYPES, type CanvasNode } from '@/features/canvas/domain/canvasNodes';
import { useCanvasStore } from '@/stores/canvasStore';

const submitFreezoneTemplateEdit = vi.hoisted(() => vi.fn());
const fetchFreezoneJobResult = vi.hoisted(() => vi.fn());
const awaitTaskCompletion = vi.hoisted(() => vi.fn());
const readUrl = vi.hoisted(() => vi.fn());

vi.mock('@/api/ops', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  submitFreezoneTemplateEdit,
  fetchFreezoneJobResult,
}));
vi.mock('@/api/tasks', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  awaitTaskCompletion,
}));
vi.mock('@/lib/url-params', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  readUrl,
}));

import { submitGridTemplateAction } from '@/features/canvas/application/gridTemplateAction';

const JOB_REF = { task_key: 'tk-1', task_type: 'freezone_template_edit', job_id: 'job-1' };

function seedSourceNode() {
  const nodes: CanvasNode[] = [
    {
      id: 'img-1',
      type: CANVAS_NODE_TYPES.imageEdit,
      position: { x: 0, y: 0 },
      data: { imageUrl: '/static/a.png', aspectRatio: '1:1' },
    } as CanvasNode,
  ];
  useCanvasStore.getState().setCanvasData(nodes, []);
}

describe('submitGridTemplateAction（宫格模板提交，从 GridActionConfirmOverlay 抽出）', () => {
  beforeEach(() => {
    readUrl.mockReturnValue({ project: 'proj-1', canvas: 'canvas-1' });
    submitFreezoneTemplateEdit.mockReset();
    fetchFreezoneJobResult.mockReset();
    awaitTaskCompletion.mockReset();
    seedSourceNode();
  });

  it('建结果节点 → 提交模板编辑（去 query 的 sourceUrl + mode 映射）→ 回填 output_url', async () => {
    submitFreezoneTemplateEdit.mockResolvedValue(JOB_REF);
    awaitTaskCompletion.mockResolvedValue({ result: { output_url: '/static/out.png' } });

    const resultId = await submitGridTemplateAction({
      sourceNodeId: 'img-1',
      imageSource: '/static/a.png?sig=x',
      key: 'multiCameraGrid',
      label: '多机位九宫格',
    });

    expect(submitFreezoneTemplateEdit).toHaveBeenCalledWith('proj-1', {
      sourceUrl: '/static/a.png',
      mode: 'multi_camera_nine_grid',
      prompt: '多机位九宫格',
    });
    expect(awaitTaskCompletion).toHaveBeenCalledWith('tk-1', 'proj-1');
    // output_url 已有 → 不再兜底查 job result。
    expect(fetchFreezoneJobResult).not.toHaveBeenCalled();

    const state = useCanvasStore.getState();
    const created = state.nodes.find((node) => node.id === resultId);
    expect(created?.type).toBe(CANVAS_NODE_TYPES.exportImage);
    expect(created?.data).toMatchObject({
      displayName: '多机位九宫格',
      imageUrl: '/static/out.png',
      previewImageUrl: '/static/out.png',
      isGenerating: false,
      generationError: null,
    });
    expect(
      state.edges.some((edge) => edge.source === 'img-1' && edge.target === resultId),
    ).toBe(true);
  });

  it('SSE 结果没有 output_url → 兜底 fetchFreezoneJobResult', async () => {
    submitFreezoneTemplateEdit.mockResolvedValue(JOB_REF);
    awaitTaskCompletion.mockResolvedValue({ result: {} });
    fetchFreezoneJobResult.mockResolvedValue({ url: '/static/fallback.png' });

    const resultId = await submitGridTemplateAction({
      sourceNodeId: 'img-1',
      imageSource: '/static/a.png',
      key: 'plotFourGrid',
      label: '剧情推演四宫格',
    });

    expect(fetchFreezoneJobResult).toHaveBeenCalledWith(
      'proj-1',
      'freezone_template_edit',
      'job-1',
    );
    const created = useCanvasStore.getState().nodes.find((node) => node.id === resultId);
    expect(created?.data).toMatchObject({ imageUrl: '/static/fallback.png' });
  });

  it('提交失败 → 错误写到结果节点', async () => {
    submitFreezoneTemplateEdit.mockRejectedValue(new Error('quota exceeded'));

    const resultId = await submitGridTemplateAction({
      sourceNodeId: 'img-1',
      imageSource: '/static/a.png',
      key: 'faceThreeView',
      label: '角色脸部三视图',
    });

    const created = useCanvasStore.getState().nodes.find((node) => node.id === resultId);
    expect(created?.data).toMatchObject({
      isGenerating: false,
      generationError: 'quota exceeded',
    });
  });

  it('缺 project → 不建节点返回 null', async () => {
    readUrl.mockReturnValue({ project: null, canvas: null });
    const before = useCanvasStore.getState().nodes.length;
    await expect(
      submitGridTemplateAction({
        sourceNodeId: 'img-1',
        imageSource: '/static/a.png',
        key: 'multiCameraGrid',
        label: 'x',
      }),
    ).resolves.toBeNull();
    expect(useCanvasStore.getState().nodes.length).toBe(before);
    expect(submitFreezoneTemplateEdit).not.toHaveBeenCalled();
  });
});
