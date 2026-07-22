// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import {
  useCallback,
  useRef,
  useState,
  type ReactElement,
  type RefObject,
} from 'react';
import {
  Camera,
  ChevronDown,
  Crop,
  Eraser,
  RotateCcw,
  Scissors,
  Split,
  Upload,
  Wand2,
} from 'lucide-react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/shadcn/dropdown-menu';
import { resolveImageDisplayUrl } from '@/features/canvas/application/imageData';
import { analyzeVideoStory } from '@/features/canvas/application/videoAnalyzeStory';
import {
  captureVideoFrameToNode,
  resolveCaptureSeekSec,
  type VideoCaptureFrameMode,
} from '@/features/canvas/application/videoCaptureFrame';
import { submitVideoClip } from '@/features/canvas/application/videoClipSubmit';
import { VIDEO_FILE_ACCEPT } from '@/features/canvas/application/videoFileTypes';
import { replaceNodeVideo } from '@/features/canvas/application/videoReplaceUpload';
import { separateVideoAudio } from '@/features/canvas/application/videoSeparateAudio';
import { runVideoSubtitleErase } from '@/features/canvas/application/videoSubtitleErase';
import type { CanvasNode, CanvasNodeData } from '@/features/canvas/domain/canvasNodes';
import { VideoClipPanel } from '@/features/canvas/nodes/VideoClipPanel';
import {
  computeDisplayedVideoRect,
  SubtitleEraseBoxOverlay,
  type SubtitleEraseBoxValue,
  type SubtitleEraseDrag,
} from '@/features/canvas/nodes/shared/subtitleEraseBox';
import { readUrl } from '@/lib/url-params';
import { useCanvasStore } from '@/stores/canvasStore';

import { createAssetBoardOpsRegistry } from './assetBoardOpsState';
import { DetailToolbarButton, DETAIL_TOOLBAR_BUTTON_CLASS } from './AssetBoardToolbarButton';

/** 进行中的视频操作（触发按钮转 spinner，settle 后恢复）。 */
type VideoBusyOp = 'clip' | 'analyze' | 'separate' | 'capture' | 'replace' | 'eraseBox';
/** 当前展开的面板（互斥，同一时刻只展开一个）。 */
type OpenPanel = 'clip' | 'eraseBox' | null;

/**
 * 视频侧的「进行中 + 失败反馈」登记表（与图片侧同一套实现，见 assetBoardOpsState）：
 * 详情工具条按 key={node.id} 整体重挂载，busy 态必须跨重挂存活，否则用户切走再
 * 切回能对同一节点重复提交、造成重复计费。
 */
const videoOpsRegistry = createAssetBoardOpsRegistry<VideoBusyOp>();

/** 导出供测试断言（nodeId → 进行中的视频操作名）。 */
export const inFlightVideoOps: ReadonlyMap<string, VideoBusyOp> = videoOpsRegistry.inFlight;

/** 仅供测试：清空进行中/失败两张登记表，避免用例间靠固定 node id 串态。 */
export function __resetAssetBoardVideoOpsStateForTest(): void {
  videoOpsRegistry.resetForTest();
}

const CAPTURE_MODES: Array<{ mode: VideoCaptureFrameMode; label: string }> = [
  { mode: 'first', label: '首帧' },
  { mode: 'last', label: '尾帧' },
  { mode: 'current', label: '当前帧' },
];

/** 详情里展开的面板：与图片侧配置行同一视觉族（细边框 + 极暗底），独占一行。 */
function OpsPanel({ children }: { children: React.ReactNode }): ReactElement {
  return (
    <div className="flex w-full flex-col gap-2 rounded-lg border border-white/10 bg-white/[0.03] p-3">
      {children}
    </div>
  );
}

/** 读结果节点上的失败原因（生成类写 generationError，解析类写 analysisError）。 */
function readNodeError(nodeId: string | null | undefined): string | null {
  if (!nodeId) return null;
  const data = useCanvasStore.getState().nodes.find((n) => n.id === nodeId)?.data as
    | { generationError?: unknown; analysisError?: unknown }
    | undefined;
  for (const value of [data?.generationError, data?.analysisError]) {
    if (typeof value === 'string' && value) return value;
  }
  return null;
}

interface AssetBoardVideoOpsProps {
  node: CanvasNode;
  /** 已由调用方解析好的片源（无片源时调用方不渲染本组件）。 */
  videoUrl: string;
  /**
   * 详情正文里那个活的 <video>（AssetBoardDetail 持有）。「当前帧」截帧要读它的
   * currentTime，「尾帧」优先读它报的 duration（比节点 data.durationMs 准）。
   * 拿不到时按 0 / 节点时长兜底，不影响其余操作。
   */
  playerRef?: RefObject<HTMLVideoElement | null>;
}

/**
 * 故事板详情的视频操作区（工作流第二批：剪辑轨道 / 解析 / 分离音视频 / 截帧 /
 * 替换视频 / 框选去字幕）。
 *
 * - 剪辑轨道复用工作流的 VideoClipPanel（纯受控组件），起止点用组件本地 state
 *   而不是写回 node.data.clipStartMs —— 避免详情里拖轨道把工作流那个节点也带进
 *   剪辑模式。
 * - 解析 / 分离音视频 / 截帧走 application/video* 的共享编排（与工作流同源），
 *   结果落新建的画布节点，spawn 后 requestFocusNode 预定位视口。
 * - 替换视频在详情里自建 file input + 复用转码/上传纯函数，不依赖工作流节点是否
 *   挂载（上一批走 canvasEventBus 的 video-node/reupload 因此没做成）。
 * - 框选去字幕把 SubtitleEraseBoxOverlay 叠在面板内自带的 <video> 上：详情正文的
 *   大播放器要留给用户正常播放/定位当前帧，不适合同时当框选画布。
 *
 * 返回 fragment：按钮直接落在调用方的 flex-wrap 工具条里，面板用 w-full 换行。
 */
export function AssetBoardVideoOps({
  node,
  videoUrl,
  playerRef,
}: AssetBoardVideoOpsProps): ReactElement {
  const data = node.data as Record<string, unknown>;
  const busyOp = videoOpsRegistry.useInFlightOp(node.id);
  const opFailure = videoOpsRegistry.useOpFailure(node.id);
  const [openPanel, setOpenPanel] = useState<OpenPanel>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // 剪辑起止点：详情本地 state（不写 node.data，见组件说明）。
  const [clipStartMs, setClipStartMs] = useState<number | null>(null);
  const [clipEndMs, setClipEndMs] = useState<number | null>(null);
  // 时长优先取节点 data，缺失时用面板打开那一刻活播放器报的值兜底。
  const nodeDurationMs = typeof data.durationMs === 'number' ? data.durationMs : null;
  const [fallbackDurationMs, setFallbackDurationMs] = useState<number | null>(null);
  const durationMs = nodeDurationMs ?? fallbackDurationMs;

  // 框选去字幕：归一化框 + 拖拽瞬时态 + 面板内播放器的固有宽高（算 object-contain）。
  const [eraseBox, setEraseBox] = useState<SubtitleEraseBoxValue | null>(null);
  const [eraseDrag, setEraseDrag] = useState<SubtitleEraseDrag | null>(null);
  const [eraseSize, setEraseSize] = useState<{ w: number; h: number } | null>(null);

  const project = readUrl().project;
  const displaySrc = resolveImageDisplayUrl(videoUrl);

  const togglePanel = useCallback(
    (panel: Exclude<OpenPanel, null>) => {
      setOpenPanel((current) => {
        if (current === panel) return null;
        // 打开面板时补一次时长兜底（节点 data.durationMs 常常是空的）。
        const live = playerRef?.current?.duration;
        if (typeof live === 'number' && Number.isFinite(live) && live > 0) {
          setFallbackDurationMs(Math.round(live * 1000));
        }
        return panel;
      });
    },
    [playerRef],
  );

  /**
   * spawn 型操作的统一收尾：结果节点建好后立即请求视口预定位（切回工作流时视口
   * 已就位），并把失败原因补到源节点工具条上——失败信息只写在新建的结果节点里，
   * 用户此刻停在源节点详情面板根本看不到。
   */
  const finishSpawn = useCallback(
    (spawnedNodeId: string | null, explicitError: string | null) => {
      if (spawnedNodeId) {
        useCanvasStore.getState().requestFocusNode(spawnedNodeId);
      }
      const message = explicitError ?? readNodeError(spawnedNodeId);
      if (message) videoOpsRegistry.reportOpFailure(node.id, message);
    },
    [node.id],
  );

  const runOp = useCallback(
    async (op: VideoBusyOp, task: () => Promise<void>) => {
      if (videoOpsRegistry.inFlight.get(node.id)) return;
      videoOpsRegistry.markOpStart(node.id, op);
      try {
        await task();
      } finally {
        videoOpsRegistry.markOpSettled(node.id);
      }
    },
    [node.id],
  );

  const handleClipSubmit = useCallback(
    (startMs: number, endMs: number) => {
      void runOp('clip', async () => {
        const result = await submitVideoClip(node.id, {
          sourceUrl: videoUrl,
          startMs,
          endMs,
          quality: typeof data.quality === 'string' ? data.quality : null,
        });
        if (result.nodeId) setOpenPanel(null);
        finishSpawn(result.nodeId, result.error);
      });
    },
    [data.quality, finishSpawn, node.id, runOp, videoUrl],
  );

  const handleAnalyze = useCallback(() => {
    void runOp('analyze', async () => {
      const spawned = analyzeVideoStory(node.id, {
        videoUrl,
        durationSec: durationMs != null ? durationMs / 1000 : undefined,
      });
      if (!spawned) return;
      // 故事节点是同步建好的 loading 态 → 立刻对焦，不等解析回来。
      useCanvasStore.getState().requestFocusNode(spawned.nodeId);
      await spawned.completion;
      const message = readNodeError(spawned.nodeId);
      if (message) videoOpsRegistry.reportOpFailure(node.id, message);
    });
  }, [durationMs, node.id, runOp, videoUrl]);

  const handleSeparate = useCallback(() => {
    void runOp('separate', async () => {
      const result = await separateVideoAudio(node.id, { sourceUrl: videoUrl });
      finishSpawn(result.videoNodeId ?? result.audioNodeId, result.error);
    });
  }, [finishSpawn, node.id, runOp, videoUrl]);

  const handleCapture = useCallback(
    (mode: VideoCaptureFrameMode) => {
      void runOp('capture', async () => {
        const player = playerRef?.current ?? null;
        const seekSec = resolveCaptureSeekSec(mode, {
          currentTimeSec: player?.currentTime ?? null,
          durationSec: player && Number.isFinite(player.duration) ? player.duration : null,
          fallbackDurationSec: durationMs != null ? durationMs / 1000 : null,
        });
        const result = await captureVideoFrameToNode(node.id, {
          videoUrl,
          seekSec,
          displayName: CAPTURE_MODES.find((item) => item.mode === mode)?.label ?? '截帧',
        });
        finishSpawn(result.nodeId, result.error);
      });
    },
    [durationMs, finishSpawn, node.id, playerRef, runOp, videoUrl],
  );

  const handleReplaceFile = useCallback(
    (file: File) => {
      void runOp('replace', async () => {
        const result = await replaceNodeVideo(node.id, file);
        if (result.error) videoOpsRegistry.reportOpFailure(node.id, result.error);
      });
    },
    [node.id, runOp],
  );

  const handleEraseBoxSubmit = useCallback(() => {
    if (!eraseBox) return;
    if (!project) {
      console.error('[asset-board] subtitle erase: no project in URL');
      return;
    }
    void runOp('eraseBox', async () => {
      try {
        const result = await runVideoSubtitleErase(project, {
          sourceUrl: videoUrl,
          mode: 'box',
          box: eraseBox,
        });
        if (result.url) {
          // 与工作流一致：框选擦除是原地替换本节点的片源，不新建节点。
          useCanvasStore
            .getState()
            .updateNodeData(node.id, { videoUrl: result.url } as Partial<CanvasNodeData>);
          setOpenPanel(null);
          setEraseBox(null);
        } else {
          console.warn('[asset-board] box subtitle erase completed without url', result);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        console.error('[asset-board] box subtitle erase failed', error);
        // 原地替换没有结果节点可承载错误 → 直接落到工具条的失败横条上。
        videoOpsRegistry.reportOpFailure(node.id, message);
      }
    });
  }, [eraseBox, node.id, project, runOp, videoUrl]);

  const anyBusy = busyOp !== null;

  return (
    <>
      <DetailToolbarButton
        icon={Scissors}
        label="剪辑轨道"
        busy={busyOp === 'clip'}
        disabled={anyBusy}
        title="拖动轨道选取片段，提交后在画布下游生成剪辑视频"
        onClick={() => togglePanel('clip')}
        trailing={<ChevronDown className="h-3 w-3" />}
      />
      <DetailToolbarButton
        icon={Wand2}
        label="解析"
        busy={busyOp === 'analyze'}
        disabled={anyBusy}
        title="解析视频生成分镜故事（在画布下游建视频故事节点）"
        onClick={handleAnalyze}
      />
      <DetailToolbarButton
        icon={Split}
        label="分离音视频"
        busy={busyOp === 'separate'}
        disabled={anyBusy}
        title="拆出背景音轨与无声视频（各建一个画布节点）"
        onClick={handleSeparate}
      />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button type="button" disabled={anyBusy} className={DETAIL_TOOLBAR_BUTTON_CLASS}>
            <Camera className="h-3.5 w-3.5" />
            截帧
            <ChevronDown className="h-3 w-3" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="start"
          sideOffset={6}
          className="z-50 min-w-[160px] border-white/10 bg-[#2e2e2e] text-white/85 shadow-xl"
        >
          {CAPTURE_MODES.map((item) => (
            <DropdownMenuItem
              key={item.mode}
              className="gap-2 rounded-[6px] text-white/80 focus:bg-white/[0.08] focus:text-white"
              onSelect={() => handleCapture(item.mode)}
            >
              <Camera className="h-4 w-4" />
              {item.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <DetailToolbarButton
        icon={Upload}
        label="替换视频"
        busy={busyOp === 'replace'}
        disabled={anyBusy}
        title="选择本地视频替换本节点片源（HEVC 等会先在浏览器内转码）"
        onClick={() => fileInputRef.current?.click()}
      />
      <DetailToolbarButton
        icon={Crop}
        label="框选擦除"
        busy={busyOp === 'eraseBox'}
        disabled={anyBusy}
        title="box 档：在画面上框出字幕区域擦除，完成后替换本视频"
        onClick={() => togglePanel('eraseBox')}
        trailing={<ChevronDown className="h-3 w-3" />}
      />

      <input
        ref={fileInputRef}
        type="file"
        accept={VIDEO_FILE_ACCEPT}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) handleReplaceFile(file);
          event.target.value = '';
        }}
      />

      {/* 操作失败兜底反馈：失败信息只写在新建结果节点上（或原地替换根本没有结果
          节点），用户还停在源节点详情面板看不到；这里补一行红色文案，8 秒后自动
          消失（见 assetBoardOpsState.reportOpFailure）。 */}
      {opFailure && (
        <div
          role="alert"
          className="w-full rounded-[6px] border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-[12px] text-red-300"
        >
          {opFailure}
        </div>
      )}

      {openPanel === 'clip' && (
        <OpsPanel>
          {durationMs ? (
            <VideoClipPanel
              videoUrl={videoUrl}
              durationMs={durationMs}
              clipStartMs={clipStartMs}
              clipEndMs={clipEndMs}
              isSubmitting={busyOp === 'clip'}
              onChange={(patch) => {
                if (patch.clipStartMs !== undefined) setClipStartMs(patch.clipStartMs);
                if (patch.clipEndMs !== undefined) setClipEndMs(patch.clipEndMs);
              }}
              onExit={() => setOpenPanel(null)}
              onSubmit={handleClipSubmit}
            />
          ) : (
            <p className="text-[12px] text-white/40">
              读不到视频时长，无法剪辑——先播放一次让播放器报出时长再试。
            </p>
          )}
        </OpsPanel>
      )}

      {openPanel === 'eraseBox' && (
        <OpsPanel>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[12px] text-white/40">
              在画面上拖出字幕所在区域（可重复拖动覆盖上一次）
            </span>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                title="重置框选"
                onClick={() => {
                  setEraseBox(null);
                  setEraseDrag(null);
                }}
                className={DETAIL_TOOLBAR_BUTTON_CLASS}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                重置
              </button>
              <DetailToolbarButton
                icon={Eraser}
                label="提交擦除"
                busy={busyOp === 'eraseBox'}
                disabled={!eraseBox}
                title={eraseBox ? '擦除框内字幕，完成后替换本视频' : '请先在画面上框选区域'}
                onClick={handleEraseBoxSubmit}
              />
            </div>
          </div>
          {/* 框选画布用面板内自带的播放器：详情正文那个大播放器要留给用户正常
              播放/定位当前帧，叠上拖拽层会把 controls 挡掉。 */}
          <div className="relative w-full overflow-hidden rounded-[6px] bg-black">
            <video
              src={displaySrc}
              playsInline
              muted
              preload="metadata"
              onLoadedMetadata={(event) => {
                const el = event.currentTarget;
                if (el.videoWidth > 0 && el.videoHeight > 0) {
                  setEraseSize({ w: el.videoWidth, h: el.videoHeight });
                }
              }}
              className="max-h-[40vh] w-full object-contain"
            />
            <SubtitleEraseBoxOverlay
              box={eraseBox}
              drag={eraseDrag}
              disabled={busyOp === 'eraseBox'}
              getDisplayedRect={(w, h) =>
                computeDisplayedVideoRect(
                  w,
                  h,
                  eraseSize?.w ?? (typeof data.widthPx === 'number' ? data.widthPx : null),
                  eraseSize?.h ?? (typeof data.heightPx === 'number' ? data.heightPx : null),
                )
              }
              onDragStart={setEraseDrag}
              onDragMove={(next) =>
                setEraseDrag((current) => (current ? { ...current, ...next } : current))
              }
              onDragEnd={(final) => {
                setEraseDrag(null);
                if (final) setEraseBox(final);
              }}
            />
          </div>
        </OpsPanel>
      )}
    </>
  );
}
