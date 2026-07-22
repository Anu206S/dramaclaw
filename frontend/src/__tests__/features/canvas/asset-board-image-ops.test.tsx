// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CANVAS_NODE_TYPES, type CanvasNode } from '@/features/canvas/domain/canvasNodes';
import {
  __resetAssetBoardImageOpsStateForTest,
  inFlightImageOps,
} from '@/features/canvas/ui/asset-board/AssetBoardImageEditMenu';
import { AssetBoardView } from '@/features/canvas/ui/asset-board/AssetBoardView';
import { useCanvasStore } from '@/stores/canvasStore';

// MultiAngleEditorPanel / LightEditorPanel 内部的 Radix Slider 依赖
// ResizeObserver（@radix-ui/react-use-size），jsdom 没有实现，同
// editor-content-split.test.tsx / canvas-skill-manual-connect.test.tsx 的兜底。
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverMock);

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

// 详情工具条的活价查询没有 QueryClientProvider —— mock 掉走硬编码兜底。
vi.mock('@/lib/queries/generation-credit-cost', () => ({
  useGenerationCreditCost: () => ({ data: undefined }),
}));
// 模型清单同样走网络，给一个确定的首选模型。
vi.mock('@/features/canvas/hooks/useFreezoneImageModels', () => ({
  useFreezoneImageModels: () => ({
    models: [{ id: 'huimeng/gpt-image-2', apiModel: 'gpt-image-2', label: 'GPT Image 2' }],
  }),
}));

// 第二批操作的编排函数：验证「选参数 → 提交」把正确入参传下去，并用永不 settle 的
// completion 保持 busy 态可断言。
const outpaintImage = vi.hoisted(() => vi.fn());
const scene360Image = vi.hoisted(() => vi.fn());
const multiAngleImage = vi.hoisted(() => vi.fn());
const relightImage = vi.hoisted(() => vi.fn());
const createUpscaleResultNode = vi.hoisted(() => vi.fn());
const submitImageUpscale = vi.hoisted(() => vi.fn());

vi.mock('@/features/canvas/application/imageOutpaint', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  outpaintImage,
}));
vi.mock('@/features/canvas/application/imageScene360', () => ({ scene360Image }));
vi.mock('@/features/canvas/application/imageMultiAngle', () => ({ multiAngleImage }));
vi.mock('@/features/canvas/application/imageRelight', () => ({ relightImage }));
vi.mock('@/features/canvas/application/imageUpscale', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  createUpscaleResultNode,
  submitImageUpscale,
}));

const NEVER = new Promise<void>(() => {});

function seedBoard(extraData: Record<string, unknown> = {}) {
  const nodes: CanvasNode[] = [
    {
      id: 'img-up',
      type: CANVAS_NODE_TYPES.upload,
      position: { x: 0, y: 0 },
      data: {
        imageUrl: '/static/up.png',
        aspectRatio: '1:1',
        displayName: '上传图',
        ...extraData,
      },
    } as CanvasNode,
    {
      // imageEdit 节点：按工作流语义不给图片编辑入口。
      id: 'img-edit',
      type: CANVAS_NODE_TYPES.imageEdit,
      position: { x: 200, y: 0 },
      data: { imageUrl: '/static/edit.png', displayName: '改图节点' },
    } as CanvasNode,
  ];
  useCanvasStore.getState().setCanvasData(nodes, []);
}

function detailPanel() {
  return screen.getByRole('region', { name: '资产详情' });
}

function openDetail(name: string) {
  render(<AssetBoardView visible onLocateNode={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name }));
}

describe('AssetBoard 详情图片操作（第二批：编辑下拉 + 全景/多角度/重打光）', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    __resetAssetBoardImageOpsStateForTest();
    seedBoard();
  });

  it('渲染 编辑/全景/多角度/重打光 入口；编辑下拉含五项', async () => {
    const user = userEvent.setup();
    openDetail('上传图');

    const detail = detailPanel();
    for (const label of ['编辑', '全景', '多角度', '重打光']) {
      expect(within(detail).getByRole('button', { name: new RegExp(label) })).toBeInTheDocument();
    }

    await user.click(within(detail).getByRole('button', { name: /编辑/ }));
    for (const label of ['重绘', '擦除', '高清', '扩图', '旋转']) {
      expect(await screen.findByRole('menuitem', { name: label })).toBeInTheDocument();
    }
  });

  it('preset_managed（主线投影锁定）节点：编辑下拉隐藏高清与旋转，其余保留', async () => {
    const user = userEvent.setup();
    seedBoard({ preset_managed: true });
    openDetail('上传图');

    await user.click(within(detailPanel()).getByRole('button', { name: /编辑/ }));
    for (const label of ['重绘', '擦除', '扩图']) {
      expect(await screen.findByRole('menuitem', { name: label })).toBeInTheDocument();
    }
    // 原地改写源图的两项被过滤（同工作流 NodeActionToolbar 语义）。
    expect(screen.queryByRole('menuitem', { name: '高清' })).not.toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: '旋转' })).not.toBeInTheDocument();
  });

  it('imageEdit 节点：不给第二批图片操作入口', () => {
    openDetail('改图节点');
    const detail = detailPanel();
    expect(within(detail).queryByRole('button', { name: /编辑/ })).not.toBeInTheDocument();
    expect(within(detail).queryByRole('button', { name: /全景/ })).not.toBeInTheDocument();
    expect(within(detail).queryByRole('button', { name: /多角度/ })).not.toBeInTheDocument();
  });

  it('扩图代表性提交流：选比例/张数 → 提交 → application 收到正确参数 + 触发按钮 busy', async () => {
    const user = userEvent.setup();
    outpaintImage.mockReturnValue({ nodeIds: ['op-1'], completion: NEVER });
    openDetail('上传图');

    const detail = detailPanel();
    await user.click(within(detail).getByRole('button', { name: /编辑/ }));
    await user.click(await screen.findByRole('menuitem', { name: '扩图' }));

    // 配置行展开。
    expect(within(detail).getByText('扩图比例')).toBeInTheDocument();
    await user.click(within(detail).getByRole('button', { name: '16:9' }));
    await user.click(within(detail).getByRole('button', { name: '2 张' }));
    await user.click(within(detail).getByRole('button', { name: '提交扩图' }));

    expect(outpaintImage).toHaveBeenCalledWith('img-up', '/static/up.png', {
      displayName: '扩图',
      targetAspectRatio: '16:9',
      imageSize: '2K',
      numImages: 2,
      model: 'gpt-image-2',
    });
    // 提交后配置行收起，「编辑」触发按钮进入 busy（spinner + 禁用）。
    expect(within(detail).queryByText('扩图比例')).not.toBeInTheDocument();
    expect(within(detail).getByRole('button', { name: /编辑/ })).toBeDisabled();
    // 结果节点已请求视口预定位（Task 10 模式）。
    expect(useCanvasStore.getState().pendingFocusNodeId).toBe('op-1');
  });

  it('高清提交流：预建结果节点 → 按选中的画质/倍数提交', async () => {
    const user = userEvent.setup();
    createUpscaleResultNode.mockReturnValue('hd-1');
    submitImageUpscale.mockReturnValue(NEVER);
    openDetail('上传图');

    const detail = detailPanel();
    await user.click(within(detail).getByRole('button', { name: /编辑/ }));
    await user.click(await screen.findByRole('menuitem', { name: '高清' }));
    await user.click(within(detail).getByRole('button', { name: '4K' }));
    await user.click(within(detail).getByRole('button', { name: '4x' }));
    await user.click(within(detail).getByRole('button', { name: '提交高清' }));

    expect(createUpscaleResultNode).toHaveBeenCalledWith('img-up', {
      displayName: '高清放大（4K · 4x）',
      modelId: 'huimeng/gpt-image-2',
      imageSize: '4K',
      scaleFactor: 4,
    });
    expect(submitImageUpscale).toHaveBeenCalledWith('hd-1', {
      sourceUrl: '/static/up.png',
      scaleFactor: 4,
      imageSize: '4K',
      model: 'gpt-image-2',
    });
    expect(useCanvasStore.getState().pendingFocusNodeId).toBe('hd-1');
  });

  it('高清提交流：submitImageUpscale 因缺 project 返回 null 时，回收刚预建的占位节点，不留孤儿', async () => {
    const user = userEvent.setup();
    // 还原 createUpscaleResultNode 的真实副作用（真的在 store 里建一个占位节点），
    // 这样才能断言「提交失败后节点被删掉」而不是「从未建过」。
    createUpscaleResultNode.mockImplementation(() =>
      useCanvasStore.getState().addNode(
        CANVAS_NODE_TYPES.exportImage,
        { x: 0, y: 0 },
        { displayName: '高清放大占位', resultKind: 'upscale' } as never,
      ),
    );
    submitImageUpscale.mockReturnValue(null);
    openDetail('上传图');

    const detail = detailPanel();
    await user.click(within(detail).getByRole('button', { name: /编辑/ }));
    await user.click(await screen.findByRole('menuitem', { name: '高清' }));
    await user.click(within(detail).getByRole('button', { name: '提交高清' }));

    expect(submitImageUpscale).toHaveBeenCalled();
    // 占位节点已被回收（同 handleRotateSubmit 的 discardRotateResultNode 处理），
    // 没有凭空多出一个永远转圈的孤儿。
    const upscalePlaceholders = useCanvasStore
      .getState()
      .nodes.filter((n) => (n.data as { resultKind?: string }).resultKind === 'upscale');
    expect(upscalePlaceholders).toHaveLength(0);
  });

  it('busy 态跨重挂载存活：切走再切回同一节点时仍处于 busy，阻止重复提交/重复计费', async () => {
    const user = userEvent.setup();
    createUpscaleResultNode.mockReturnValue('hd-inflight');
    submitImageUpscale.mockReturnValue(NEVER);

    const { unmount } = render(<AssetBoardView visible onLocateNode={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '上传图' }));
    let detail = detailPanel();
    await user.click(within(detail).getByRole('button', { name: /编辑/ }));
    await user.click(await screen.findByRole('menuitem', { name: '高清' }));
    await user.click(within(detail).getByRole('button', { name: '提交高清' }));

    // 已登记到跨重挂载存活的模块级 Map（不是组件局部 state）。
    expect(inFlightImageOps.get('img-up')).toBe('hd');
    expect(submitImageUpscale).toHaveBeenCalledTimes(1);

    // 模拟详情工具条按 key={node.id} 整体重挂载：卸载再重新渲染（同一节点）。
    unmount();
    render(<AssetBoardView visible onLocateNode={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '上传图' }));
    detail = detailPanel();

    // 新实例挂载时从模块级登记表里读到了「仍在跑」，触发按钮保持 disabled。
    expect(within(detail).getByRole('button', { name: /编辑/ })).toBeDisabled();
    expect(within(detail).getByRole('button', { name: /全景/ })).toBeDisabled();

    // 即便试图再走一次编辑下拉，disabled 状态本身已经挡住了交互入口——
    // 编排函数没有被第二次调用，不会重复计费。
    expect(submitImageUpscale).toHaveBeenCalledTimes(1);
    expect(createUpscaleResultNode).toHaveBeenCalledTimes(1);
  });

  it('操作失败兜底反馈：completion settle 时结果节点带 generationError，源节点工具条上出现红色错误文案，8 秒后自动消失', async () => {
    // 菜单导航先用真实计时器走完（findByRole 内部的 waitFor 轮询在假计时器下
    // 容易卡住），只在「提交」→「校验自动消失」这一段切假计时器。
    createUpscaleResultNode.mockImplementation(() =>
      useCanvasStore.getState().addNode(
        CANVAS_NODE_TYPES.exportImage,
        { x: 0, y: 0 },
        { displayName: '高清放大占位', resultKind: 'upscale' } as never,
      ),
    );
    // 贴近真实应用层的 completion 契约：失败不 reject，而是把错误写到结果节点
    // data 上再 resolve（见 imageUpscale.ts 的 catch 分支）。
    submitImageUpscale.mockImplementation((nodeId: string) =>
      Promise.resolve().then(() => {
        useCanvasStore.getState().updateNodeData(nodeId, {
          generationError: '生成失败：额度不足',
        });
      }),
    );

    const user = userEvent.setup();
    openDetail('上传图');
    const detail = detailPanel();
    await user.click(within(detail).getByRole('button', { name: /编辑/ }));
    await user.click(await screen.findByRole('menuitem', { name: '高清' }));

    vi.useFakeTimers();
    try {
      fireEvent.click(within(detail).getByRole('button', { name: '提交高清' }));

      // completion 是 Promise.resolve().then(...) 微任务链，跟假计时器无关
      // （假计时器只拦 setTimeout/setInterval），flush 掉让 trackSpawn 的
      // finally 和 reportOpFailure 跑完，再同步查询（不用 findBy，避免其内部
      // 轮询依赖假计时器）。
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(screen.getByRole('alert')).toHaveTextContent('生成失败：额度不足');

      act(() => {
        vi.advanceTimersByTime(8000);
      });
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('全景：确认后直接提交（取消确认则不提交）', async () => {
    const user = userEvent.setup();
    scene360Image.mockReturnValue({ nodeId: 'pano-1', completion: NEVER });
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    openDetail('上传图');

    const detail = detailPanel();
    await user.click(within(detail).getByRole('button', { name: /全景/ }));
    expect(scene360Image).not.toHaveBeenCalled();

    confirmSpy.mockReturnValue(true);
    await user.click(within(detail).getByRole('button', { name: /全景/ }));
    expect(scene360Image).toHaveBeenCalledWith('img-up', '/static/up.png', {
      displayName: '360°全景图',
      aspectRatio: '2:1',
    });
    expect(useCanvasStore.getState().pendingFocusNodeId).toBe('pano-1');
    confirmSpy.mockRestore();
  });

  it('多角度：点按钮打开工作流完整弹窗编辑器（portal 到 body），旧内联球面区块不再渲染', async () => {
    const user = userEvent.setup();
    multiAngleImage.mockReturnValue({ nodeId: 'mv-1', completion: NEVER });
    openDetail('上传图');

    const detail = detailPanel();
    await user.click(within(detail).getByRole('button', { name: /多角度/ }));

    // 弹窗 portal 到 document.body：详情面板内找不到，但全局能找到。
    const dialog = await screen.findByRole('dialog', { name: '多维度编辑器' });
    expect(within(detail).queryByRole('dialog')).toBeNull();
    // 旧内联球面选角区块（环绕/俯仰读数）不再共存。
    expect(screen.queryByText(/环绕 0° · 俯仰 0°/)).not.toBeInTheDocument();

    // 提交带上编辑器面板的当前参数（默认水平/垂直 0°、中景），并请求视口预定位。
    await user.click(within(dialog).getByRole('button', { name: 'multiAngleEditor.submit' }));
    expect(multiAngleImage).toHaveBeenCalledWith(
      'img-up',
      '/static/up.png',
      expect.objectContaining({
        preset: 'custom',
        horizontalDeg: 0,
        verticalDeg: 0,
        zoom: 'medium',
        apiModel: 'gpt-image-2',
      }),
    );
    // 提交成功后弹窗自己关闭（onSubmitted → onClose 契约），且视口已预定位到新节点。
    expect(screen.queryByRole('dialog', { name: '多维度编辑器' })).not.toBeInTheDocument();
    expect(useCanvasStore.getState().pendingFocusNodeId).toBe('mv-1');
  });

  it('多角度：点弹窗遮罩关闭 —— 面板自身的点外监听与遮罩 onClick 同时命中也只关一次', async () => {
    const user = userEvent.setup();
    openDetail('上传图');

    const detail = detailPanel();
    await user.click(within(detail).getByRole('button', { name: /多角度/ }));
    const dialog = await screen.findByRole('dialog', { name: '多维度编辑器' });

    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    // 直接点遮罩本身（target === currentTarget），同时触发面板的 document 捕获监听。
    fireEvent.click(dialog);
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();

    expect(screen.queryByRole('dialog', { name: '多维度编辑器' })).not.toBeInTheDocument();
    expect(multiAngleImage).not.toHaveBeenCalled();
    // 没有卡死在半关闭状态：再次点按钮仍能正常重新打开。
    await user.click(within(detail).getByRole('button', { name: /多角度/ }));
    expect(await screen.findByRole('dialog', { name: '多维度编辑器' })).toBeInTheDocument();
  });

  it('重打光：点按钮打开工作流完整弹窗编辑器（portal 到 body），旧内联平面配置行不再渲染', async () => {
    const user = userEvent.setup();
    relightImage.mockReturnValue({ nodeId: 'rl-1', completion: NEVER });
    openDetail('上传图');

    const detail = detailPanel();
    await user.click(within(detail).getByRole('button', { name: /重打光/ }));

    const dialog = await screen.findByRole('dialog', { name: '打光效果编辑器' });
    expect(within(detail).queryByRole('dialog')).toBeNull();
    // 旧内联平面配置行（主光方向分段）不再共存。
    expect(screen.queryByText('主光方向')).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: 'lightEditor.submit' }));
    expect(relightImage).toHaveBeenCalledWith(
      'img-up',
      '/static/up.png',
      expect.objectContaining({
        rimLight: false,
        mainLight: expect.objectContaining({ nearestPreset: 'front' }),
        smartMode: expect.objectContaining({ enabled: false }),
      }),
    );
    expect(screen.queryByRole('dialog', { name: '打光效果编辑器' })).not.toBeInTheDocument();
    expect(useCanvasStore.getState().pendingFocusNodeId).toBe('rl-1');
  });

  it('重打光：点弹窗遮罩关闭 —— 只关一次，且不留在半关闭状态', async () => {
    const user = userEvent.setup();
    openDetail('上传图');

    const detail = detailPanel();
    await user.click(within(detail).getByRole('button', { name: /重打光/ }));
    const dialog = await screen.findByRole('dialog', { name: '打光效果编辑器' });

    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    fireEvent.click(dialog);
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();

    expect(screen.queryByRole('dialog', { name: '打光效果编辑器' })).not.toBeInTheDocument();
    expect(relightImage).not.toHaveBeenCalled();
    await user.click(within(detail).getByRole('button', { name: /重打光/ }));
    expect(await screen.findByRole('dialog', { name: '打光效果编辑器' })).toBeInTheDocument();
  });

  it('重绘：点菜单项挂出 portal 全屏编辑器（冒烟）', async () => {
    const user = userEvent.setup();
    openDetail('上传图');

    await user.click(within(detailPanel()).getByRole('button', { name: /编辑/ }));
    await user.click(await screen.findByRole('menuitem', { name: '重绘' }));

    // RedrawOverlay portal 到 document.body：详情面板外能找到它的退出按钮。
    expect(await screen.findByRole('button', { name: /退出重绘/ })).toBeInTheDocument();
    expect(within(detailPanel()).queryByRole('button', { name: /退出重绘/ })).toBeNull();
  });
});
