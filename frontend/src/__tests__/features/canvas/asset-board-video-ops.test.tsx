// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CANVAS_NODE_TYPES, type CanvasNode } from '@/features/canvas/domain/canvasNodes';
import {
  __resetAssetBoardVideoOpsStateForTest,
  inFlightVideoOps,
} from '@/features/canvas/ui/asset-board/AssetBoardVideoOpsMenu';
import { AssetBoardView } from '@/features/canvas/ui/asset-board/AssetBoardView';
import { useCanvasStore } from '@/stores/canvasStore';

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverMock);

vi.mock('react-i18next', () => ({
  // 第二参数可能是插值对象（如 t(key, { count })，视频生成表单的「生成数量」用到），
  // 只有字符串才当默认文案；否则会把对象当 React 子节点渲染而炸掉整棵树。
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) =>
      typeof fallback === 'string' ? fallback : key,
  }),
}));
vi.mock('@/lib/queries/generation-credit-cost', () => ({
  useGenerationCreditCost: () => ({ data: undefined }),
}));
vi.mock('@/features/canvas/hooks/useFreezoneImageModels', () => ({
  useFreezoneImageModels: () => ({ models: [] }),
}));

// 第二批视频操作的编排函数：验证「点按钮 → 把正确入参传下去」，并用永不 settle 的
// promise 保持 busy 态可断言。
const submitVideoClip = vi.hoisted(() => vi.fn());
const analyzeVideoStory = vi.hoisted(() => vi.fn());
const separateVideoAudio = vi.hoisted(() => vi.fn());
const captureVideoFrameToNode = vi.hoisted(() => vi.fn());
const replaceNodeVideo = vi.hoisted(() => vi.fn());

vi.mock('@/features/canvas/application/videoClipSubmit', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  submitVideoClip,
}));
vi.mock('@/features/canvas/application/videoAnalyzeStory', () => ({ analyzeVideoStory }));
vi.mock('@/features/canvas/application/videoSeparateAudio', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  separateVideoAudio,
}));
vi.mock('@/features/canvas/application/videoCaptureFrame', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  captureVideoFrameToNode,
}));
vi.mock('@/features/canvas/application/videoReplaceUpload', () => ({ replaceNodeVideo }));

const NEVER = new Promise<never>(() => {});

function seedBoard() {
  const nodes: CanvasNode[] = [
    {
      id: 'vid-1',
      type: CANVAS_NODE_TYPES.video,
      position: { x: 0, y: 0 },
      data: {
        videoUrl: '/static/src.mp4',
        durationMs: 8000,
        displayName: '源视频',
        quality: '1080P',
      },
    } as CanvasNode,
    {
      // 合成节点：不是 isVideoNode → 不该出现第二批视频操作。
      id: 'compose-1',
      type: CANVAS_NODE_TYPES.videoCompose,
      position: { x: 300, y: 0 },
      data: { displayName: '合成节点' },
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

describe('AssetBoard 详情视频操作（第二批）', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    __resetAssetBoardVideoOpsStateForTest();
    seedBoard();
  });

  it('视频节点渲染六项入口', () => {
    openDetail('源视频');
    const detail = detailPanel();
    for (const label of ['剪辑轨道', '解析', '分离音视频', '截帧', '替换视频', '框选擦除']) {
      expect(within(detail).getByRole('button', { name: new RegExp(label) })).toBeTruthy();
    }
  });

  it('videoCompose 节点不出第二批视频操作（对齐工作流 isVideoNode 分支）', () => {
    openDetail('合成节点');
    const detail = detailPanel();
    for (const label of ['解析', '分离音视频', '截帧', '替换视频', '框选擦除']) {
      expect(within(detail).queryByRole('button', { name: new RegExp(label) })).toBeNull();
    }
  });

  it('解析 → 走共享编排并对焦新建的故事节点；在途期间禁重复提交', async () => {
    analyzeVideoStory.mockReturnValue({ nodeId: 'story-1', completion: NEVER });
    openDetail('源视频');

    fireEvent.click(within(detailPanel()).getByRole('button', { name: /解析/ }));

    expect(analyzeVideoStory).toHaveBeenCalledWith('vid-1', {
      videoUrl: '/static/src.mp4',
      durationSec: 8,
    });
    await waitFor(() => expect(inFlightVideoOps.get('vid-1')).toBe('analyze'));
    // 结果节点同步建好 → 立即请求视口预定位（切回工作流时视口已就位）。
    expect(useCanvasStore.getState().pendingFocusNodeId).toBe('story-1');
    // 在途期间其余入口一并禁用，避免重复计费。
    expect(
      within(detailPanel()).getByRole('button', { name: /分离音视频/ }),
    ).toHaveProperty('disabled', true);
  });

  it('分离音视频 → 走共享编排', async () => {
    separateVideoAudio.mockReturnValue(NEVER);
    openDetail('源视频');
    fireEvent.click(within(detailPanel()).getByRole('button', { name: /分离音视频/ }));
    expect(separateVideoAudio).toHaveBeenCalledWith('vid-1', { sourceUrl: '/static/src.mp4' });
    await waitFor(() => expect(inFlightVideoOps.get('vid-1')).toBe('separate'));
  });

  it('截帧下拉三档 → 首帧 seek 到 0', async () => {
    const user = userEvent.setup();
    captureVideoFrameToNode.mockReturnValue(NEVER);
    openDetail('源视频');

    await user.click(within(detailPanel()).getByRole('button', { name: /截帧/ }));
    for (const label of ['首帧', '尾帧', '当前帧']) {
      expect(screen.getByRole('menuitem', { name: label })).toBeTruthy();
    }
    await user.click(screen.getByRole('menuitem', { name: '首帧' }));

    expect(captureVideoFrameToNode).toHaveBeenCalledWith('vid-1', {
      videoUrl: '/static/src.mp4',
      seekSec: 0,
      displayName: '首帧',
    });
  });

  it('替换视频 → 选文件后走转码/上传纯函数（不依赖工作流节点是否挂载）', async () => {
    replaceNodeVideo.mockReturnValue(NEVER);
    openDetail('源视频');

    const input = detailPanel().querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).toBeTruthy();
    const file = new File(['x'], 'new.mp4', { type: 'video/mp4' });
    fireEvent.change(input, { target: { files: [file] } });

    expect(replaceNodeVideo).toHaveBeenCalledWith('vid-1', file);
    await waitFor(() => expect(inFlightVideoOps.get('vid-1')).toBe('replace'));
  });

  it('剪辑失败 → 源节点工具条上出红色失败横条', async () => {
    submitVideoClip.mockResolvedValue({ nodeId: null, error: '剪辑完成但未返回视频地址' });
    openDetail('源视频');

    // 直接驱动面板里的提交按钮太依赖轨道拖拽；这里走 store 之外的最短路径：
    // 打开剪辑轨道面板后，VideoClipPanel 的提交按钮在有时长时可点。
    fireEvent.click(within(detailPanel()).getByRole('button', { name: /剪辑轨道/ }));
    const submit = within(detailPanel()).getByTitle('提交剪辑');
    fireEvent.click(submit);

    await waitFor(() =>
      expect(within(detailPanel()).getByRole('alert').textContent).toContain(
        '剪辑完成但未返回视频地址',
      ),
    );
  });

  it('框选擦除面板：未框选时提交禁用', () => {
    openDetail('源视频');
    fireEvent.click(within(detailPanel()).getByRole('button', { name: /框选擦除/ }));
    expect(within(detailPanel()).getByRole('button', { name: /提交擦除/ })).toHaveProperty(
      'disabled',
      true,
    );
  });
});
