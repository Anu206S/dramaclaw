// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { submitFreezoneTemplateEdit } from '@/api/ops';
import { CANVAS_NODE_TYPES, type CanvasNode } from '@/features/canvas/domain/canvasNodes';
import { AssetBoardView } from '@/features/canvas/ui/asset-board/AssetBoardView';
import { useCanvasStore } from '@/stores/canvasStore';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

vi.mock('@/lib/queries/generation-credit-cost', () => ({
  useGenerationCreditCost: () => ({ data: undefined }),
}));

vi.mock('@/lib/url-params', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/url-params')>()),
  readUrl: () => ({ project: 'demo-project', canvas: 'default' }),
}));

vi.mock('@/api/ops', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/ops')>()),
  fetchFreezoneImageModels: vi.fn(async () => [
    {
      id: 'huimeng/test-image',
      providerId: 'huimeng',
      apiModel: 'test_image_api',
      label: '测试模型',
    },
  ]),
  listFreezoneStyleTemplates: vi.fn(async () => []),
  fetchFreezoneCameraOptions: vi.fn(async () => null),
  listFreezoneGenerationHistory: vi.fn(async () => []),
  submitFreezoneTemplateEdit: vi.fn(async () => ({
    task_key: 'task-1',
    task_type: 'freezone_template_edit',
    job_id: 'job-1',
  })),
  fetchFreezoneJobResult: vi.fn(async () => ({ url: '/static/out.png' })),
}));

vi.mock('@/api/tasks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/tasks')>()),
  awaitTaskCompletion: vi.fn(async () => ({
    result: { output_url: '/static/out.png' },
  })),
}));

const SOURCE_NODE: CanvasNode = {
  id: 'src-1',
  type: CANVAS_NODE_TYPES.upload,
  position: { x: 0, y: 0 },
  data: {
    imageUrl: '/static/source.png',
    aspectRatio: '16:9',
    displayName: '源图',
  },
};

function detailPanel() {
  return screen.getByRole('region', { name: '资产详情' });
}

function nodeData(nodeId: string): Record<string, unknown> {
  const node = useCanvasStore.getState().nodes.find((candidate) => candidate.id === nodeId);
  return (node?.data ?? {}) as Record<string, unknown>;
}

function spawnedOpNode(): CanvasNode {
  const spawned = useCanvasStore
    .getState()
    .nodes.find((candidate) => candidate.id !== SOURCE_NODE.id);
  if (!spawned) throw new Error('功能节点没有被创建');
  return spawned;
}

/** 打开源图详情 → 展开「宫格模板」下拉 → 点某个功能。 */
async function pickGridOp(label: string) {
  const user = userEvent.setup();
  useCanvasStore.getState().setCanvasData([SOURCE_NODE], []);
  render(<AssetBoardView visible onLocateNode={() => {}} />);
  fireEvent.click(screen.getByRole('button', { name: '源图' }));
  await user.click(within(detailPanel()).getByRole('button', { name: '宫格模板' }));
  await user.click(await screen.findByRole('menuitem', { name: new RegExp(label) }));
  return user;
}

describe('故事板 · 功能 chip（点功能建节点 → 确认后生成）', () => {
  beforeEach(() => {
    vi.mocked(submitFreezoneTemplateEdit).mockClear();
  });

  it('点功能只建节点、不提交：新节点是 imageGen、节点名=功能名、记住源图并连边', async () => {
    await pickGridOp('多机位九宫格');

    const spawned = spawnedOpNode();
    expect(spawned.type).toBe(CANVAS_NODE_TYPES.imageGen);
    const data = spawned.data as Record<string, unknown>;
    expect(data.displayName).toBe('多机位九宫格');
    expect(data.imageOpKey).toBe('multiCameraGrid');
    expect(data.imageOpSourceUrl).toBe('/static/source.png');
    expect(data.isGenerating).toBe(false);
    // 连在源节点下游。
    expect(
      useCanvasStore
        .getState()
        .edges.some((edge) => edge.source === SOURCE_NODE.id && edge.target === spawned.id),
    ).toBe(true);
    // 关键：这一步不提交。
    expect(submitFreezoneTemplateEdit).not.toHaveBeenCalled();
  });

  it('详情随即切到新节点，输入框顶部是可切换的功能 chip + 功能说明', async () => {
    await pickGridOp('角色三视图生成');

    const detail = detailPanel();
    expect(within(detail).getByRole('button', { name: /角色三视图生成/ })).toBeInTheDocument();
    expect(within(detail).getByTitle('切换功能')).toBeInTheDocument();
    expect(within(detail).getByTitle('移除功能（改为普通图片生成）')).toBeInTheDocument();
    expect(
      within(detail).getByText(/直接基于当前图像生成完整的角色三视图/),
    ).toBeInTheDocument();
  });

  it('提示词留空也能提交（↑ 走对应模板，prompt 兜底用功能名）', async () => {
    await pickGridOp('产品三视图');

    const submit = within(detailPanel()).getByRole('button', { name: '生成' });
    expect(submit).not.toBeDisabled();
    fireEvent.click(submit);

    await waitFor(() => expect(submitFreezoneTemplateEdit).toHaveBeenCalled());
    const [project, payload] = vi.mocked(submitFreezoneTemplateEdit).mock.calls[0];
    expect(project).toBe('demo-project');
    expect(payload.sourceUrl).toBe('/static/source.png');
    expect(payload.mode).toBe('product_three_view');
    expect(payload.prompt).toBe('产品三视图');
    // 产物回填到功能节点自己身上，而不是再建一个结果节点。
    await waitFor(() => expect(nodeData(spawnedOpNode().id).imageUrl).toBe('/static/out.png'));
    expect(useCanvasStore.getState().nodes).toHaveLength(2);
  });

  it('点 chip 展开功能框（四栏），选另一个功能 → key 与节点名一起换', async () => {
    const user = await pickGridOp('剧情推演四宫格');
    const spawnedId = spawnedOpNode().id;

    await user.click(within(detailPanel()).getByTitle('切换功能'));
    for (const category of ['分镜叙事', '空间与机位', '设定图', '质感调节']) {
      expect(await screen.findByText(category)).toBeInTheDocument();
    }
    await user.click(screen.getByRole('button', { name: '打光' }));

    expect(nodeData(spawnedId).imageOpKey).toBe('relight');
    expect(nodeData(spawnedId).displayName).toBe('打光');
  });

  it('关掉 chip → 退化成普通图片生成节点（chip 消失，空提示词重新禁用提交）', async () => {
    await pickGridOp('电影级光影校正');
    const spawnedId = spawnedOpNode().id;

    fireEvent.click(within(detailPanel()).getByTitle('移除功能（改为普通图片生成）'));

    expect(nodeData(spawnedId).imageOpKey).toBeNull();
    expect(within(detailPanel()).queryByTitle('切换功能')).not.toBeInTheDocument();
    expect(within(detailPanel()).getByRole('button', { name: '生成' })).toBeDisabled();
  });
});
