// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
import {
  Handle,
  Position,
  useUpdateNodeInternals,
  type NodeProps,
} from "@xyflow/react";
import {
  AlertTriangle,
  ArrowUp,
  Camera,
  ChevronDown,
  Download,
  Layers,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  Sparkles,
  Square,
  Upload as UploadIcon,
  Video as VideoIcon,
  Volume2,
  VolumeX,
  X as XIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  CANVAS_NODE_TYPES,
  isVideoNode,
  type CanvasNode,
  type VideoNodeData,
} from "@/features/canvas/domain/canvasNodes";
import {
  publishNodeActionAccepted,
  publishNodeActionError,
  publishNodeActionSuccess,
  subscribeNodeAction,
} from "@/features/canvas/application/nodeActionResult";
import { resolveImageDisplayUrl } from "@/features/canvas/application/imageData";
import { isVideoFile, VIDEO_FILE_ACCEPT } from "@/features/canvas/application/videoFileTypes";
import {
  captureVideoFrameToNode,
  resolveCaptureSeekSec,
} from "@/features/canvas/application/videoCaptureFrame";
import { submitVideoClip } from "@/features/canvas/application/videoClipSubmit";
import { replaceNodeVideo } from "@/features/canvas/application/videoReplaceUpload";
import {
  computeDisplayedVideoRect,
  SubtitleEraseBoxOverlay,
} from "@/features/canvas/nodes/shared/subtitleEraseBox";
import { resolveNodeDisplayName } from "@/features/canvas/domain/nodeDisplay";
import { downloadUrlAsFile } from "@/lib/browserDownload";
import { useAlbumPendingTotal } from "@/features/canvas/nodes/shared/albumPendingTotals";
import { canvasEventBus } from "@/features/canvas/application/canvasServices";
import { VideoGenerationForm } from "@/features/canvas/nodes/shared/VideoGenerationForm";
import { useVideoGenerationForm } from "@/features/canvas/nodes/shared/useVideoGenerationForm";
import { spawnVideoAssetLibraryReferences } from "@/features/canvas/nodes/shared/assetLibraryReferenceSpawn";
import {
  NodeHeader,
  NODE_HEADER_FLOATING_POSITION_CLASS,
} from "@/features/canvas/ui/NodeHeader";
import { NodeResizeHandle } from "@/features/canvas/ui/NodeResizeHandle";
import { PanelExpandButton } from "@/features/canvas/ui/PanelExpandButton";
import {
  NODE_OPS_PANEL_ENTER_CLASS,
  OperationPanelShell,
} from "@/features/canvas/ui/OperationPanelShell";
import { NodeGenerationOverlay } from "@/features/canvas/ui/NodeGenerationOverlay";
import {
  CANVAS_NODE_INPUT_BODY_FRAME_CLASS,
  CANVAS_NODE_INPUT_BODY_SELECTED_FRAME_CLASS,
  CANVAS_NODE_INPUT_SURFACE_CLASS,
  CANVAS_NODE_OPS_PANEL_CLASS,
  CANVAS_NODE_PANEL_SURFACE_CLASS,
  CANVAS_NODE_TOOLBAR_PILL_CLASS,
  canvasNodeFrameClass,
} from "@/features/canvas/ui/nodeFrameStyles";
import {
  hasMainlineContexts,
  NodeContextBadges,
} from "@/features/freezone/context/NodeContextBadges";
import { RegenerateButton } from "@/features/canvas/ui/RegenerateButton";
import {
  NODE_CREDIT_PILL_FLAT_CLASS,
  NODE_GENERATE_BUTTON_BASE_CLASS,
  NODE_GENERATE_BUTTON_DISABLED_CLASS,
  NODE_GENERATE_BUTTON_ENABLED_CLASS,
} from "@/features/canvas/ui/nodeControlStyles";
import {
  NODE_SIDE_ACTION_BUTTON_CLASS,
  NODE_SIDE_ACTION_ICON_CLASS,
  NodeSideActionRail,
} from "@/features/canvas/ui/NodeSideActionRail";
import { VideoClipPanel } from "@/features/canvas/nodes/VideoClipPanel";
import {
  AssetLibraryModal,
  type AssetLibrarySelection,
} from "@/features/canvas/ui/AssetLibraryModal";
import { useCanvasStore, useIsBoxSelecting } from "@/stores/canvasStore";
import { runVideoSubtitleErase } from "@/features/canvas/application/videoSubtitleErase";
import { useNodeGenerationHistory } from "@/features/canvas/hooks/useNodeGenerationHistory";
import {
  NodeGenerationHistory,
  hasCompletedHistoryRecords,
  historyRecordOutputUrl,
} from "@/features/canvas/ui/NodeGenerationHistory";
import type { FreezoneGenerationHistoryRecord } from "@/api/ops";
import { readUrl } from "@/lib/url-params";
import { CreditCostPill } from "@/components/credits/credit-visual";

type VideoNodeProps = NodeProps & {
  id: string;
  data: VideoNodeData;
  selected?: boolean;
};

const DEFAULT_WIDTH = 580;
const DEFAULT_HEIGHT = 380;
const MIN_WIDTH = 480;
const MIN_HEIGHT = 280;
const MAX_WIDTH = 1100;
const MAX_HEIGHT = 1000;

// 图片节点的默认落位尺寸（与 ImageGenNode 的 DEFAULT_WIDTH/HEIGHT 对齐）。
// 「首帧生成视频」会在视频节点左侧新建一个图片节点，排版要按它的真实尺寸算。
const IMAGE_GEN_NODE_WIDTH = 580;
const IMAGE_GEN_NODE_HEIGHT = 360;
/** 「首帧生成视频」预填的提示词，用户可以直接改。 */
const FIRST_FRAME_PROMPT = "以当前图为首帧生成视频";

const OPERATIONS_PANEL_HEIGHT = 280;
const OPERATIONS_PANEL_GAP = 12;
// Extend the ops panel beyond the node's left/right edges so the textarea +
// chips have more room than the video frame itself.
const OPERATIONS_PANEL_OVERHANG = 120;
// 「放大」后用居中弹窗展示，给提示词编辑更舒适的空间。
const OPERATIONS_PANEL_EXPANDED_HEIGHT = 560;
const OPERATIONS_PANEL_EXPANDED_WIDTH = 1040;

function resolveDroppedVideoFile(event: DragEvent<HTMLElement>): File | null {
  const directFile = event.dataTransfer.files?.[0];
  if (directFile && isVideoFile(directFile)) {
    return directFile;
  }
  // items[].type 同样对 .mxf 为空串，先按 MIME 粗筛拿到 File 再用扩展名兜底。
  const candidates = Array.from(event.dataTransfer.items || []).filter(
    (candidate) => candidate.kind === "file",
  );
  for (const candidate of candidates) {
    const file = candidate.getAsFile();
    if (file && isVideoFile(file)) return file;
  }
  return null;
}

export const VideoNode = memo(
  ({ id, data, selected, width, height }: VideoNodeProps) => {
    const { t } = useTranslation();
    const updateNodeInternals = useUpdateNodeInternals();
    const setSelectedNode = useCanvasStore((state) => state.setSelectedNode);
    const isBoxSelecting = useIsBoxSelecting();
    const updateNodeData = useCanvasStore((state) => state.updateNodeData);
    const addNode = useCanvasStore((state) => state.addNode);
    const addEdge = useCanvasStore((state) => state.addEdge);
    const setActiveOverlayNodeId = useCanvasStore(
      (state) => state.setActiveOverlayNodeId,
    );
    const inputRef = useRef<HTMLInputElement>(null);
    // Mirror the actual <video> element into state so VideoPlayerControls 能
    // 在挂载/卸载时重新订阅事件（仅 ref 不会触发重渲染）。同时保留可写的
    // ref，给非 React 路径（capture frame 之类）继续用 .current。
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const [videoEl, setVideoEl] = useState<HTMLVideoElement | null>(null);
    const setVideoRef = useCallback((el: HTMLVideoElement | null) => {
      videoRef.current = el;
      setVideoEl(el);
    }, []);
    const transientUrlRef = useRef<string | null>(null);
    const [transientPreviewUrl, setTransientPreviewUrl] = useState<
      string | null
    >(null);
    const [isCapturingFrame, setIsCapturingFrame] = useState(false);
    const [isCharacterLibraryOpen, setIsCharacterLibraryOpen] = useState(false);
    const [isComposingClip, setIsComposingClip] = useState(false);
    const [clipError, setClipError] = useState<string | null>(null);

    // 每节点生成历史：仅在节点被选中时拉取，避免画布上每个视频节点都各发一次
    // 请求。生成完成后调用 refreshHistory 把新记录拉进来。
    const {
      records: historyRecords,
      isLoading: historyLoading,
      refresh: refreshHistory,
    } = useNodeGenerationHistory(id, { enabled: Boolean(selected) });

    // 生成进行中时，点击历史记录走「非破坏性预览」：不覆写 videoUrl、不打断在途
    // 任务，仅把这条历史视频临时显示在主体上（见 isGenerating 渲染分支）。新视频
    // 生成完成后由下方 effect 自动清空，回到最新结果。非生成态恢复历史时也清掉它。
    const [historyPreviewUrl, setHistoryPreviewUrl] = useState<string | null>(
      null,
    );

    const {
      formProps: videoFormProps,
      isGenerating,
      submitDisabled,
      submit: handleSubmit,
      prompt,
      quality,
      upstreamCounts,
    } = useVideoGenerationForm(id, { onGenerationSettled: refreshHistory });

    const openCharacterLibrary = useCallback(() => {
      setIsCharacterLibraryOpen(true);
    }, []);
    const generationError =
      typeof data.generationError === 'string' ? data.generationError.trim() : '';
    // Only treat as a failure-state once generation has stopped and produced no
    // video — a stale error must never hide a successfully generated clip.
    const hasGenerationError =
      !isGenerating && !data.videoUrl && generationError.length > 0;
    const generationErrorRequestId =
      typeof data.generationErrorRequestId === "string" && data.generationErrorRequestId
        ? data.generationErrorRequestId
        : "";

    // 生成结束（成功/失败）后清掉临时历史预览，让主体回到最新结果。
    useEffect(() => {
      if (!isGenerating) setHistoryPreviewUrl(null);
    }, [isGenerating]);

    const handleRestoreHistory = useCallback(
      (record: FreezoneGenerationHistoryRecord) => {
        const url = historyRecordOutputUrl(record);
        if (!url) return;
        // 生成进行中：仅做非破坏性预览，绝不动 videoUrl，也不打断在途任务。
        if (isGenerating) {
          setHistoryPreviewUrl(url);
          return;
        }
        setHistoryPreviewUrl(null);
        updateNodeData(id, {
          videoUrl: url,
          isGenerating: false,
          generationStartedAt: null,
          sourceFileName: null,
          generationError: null,
          generationErrorDetails: null,
          generationErrorRequestId: null,
          // 恢复单条历史结果时旧批次画册已与主视频脱钩——一并清掉。
          generationBatch: null,
        });
      },
      [id, isGenerating, updateNodeData],
    );

    // 节点被连线（存在入边）后：隐藏「试试」CTA，只在节点中间显示一个图标（对齐 libtv）。
    const isConnected = useCanvasStore((state) =>
      state.edges.some((edge) => edge.target === id)
    );
    const isClipMode = Boolean(data.isClipMode);
    const clipStartMs =
      typeof data.clipStartMs === "number" ? data.clipStartMs : null;
    const clipEndMs =
      typeof data.clipEndMs === "number" ? data.clipEndMs : null;
    const durationMs =
      typeof data.durationMs === "number" ? data.durationMs : null;

    const resolvedTitle = useMemo(
      () => resolveNodeDisplayName(CANVAS_NODE_TYPES.video, data),
      [data],
    );
    const resolvedWidth = Math.max(
      MIN_WIDTH,
      Math.round(width ?? DEFAULT_WIDTH),
    );
    const resolvedHeight = Math.max(
      MIN_HEIGHT,
      Math.round(height ?? DEFAULT_HEIGHT),
    );
    // 收起态浮动面板固定基础尺寸；放大用居中弹窗（见下方 OperationPanelShell）。
    const [panelExpanded, setPanelExpanded] = useState(false);
    const panelHeight = OPERATIONS_PANEL_HEIGHT;
    const panelOverhang = OPERATIONS_PANEL_OVERHANG;

    // ── 叠卡画册（count > 1 的一组生成结果，与图片节点同构）──
    // 收拢时主视频后探出 N-1 张卡片边；hover 出现右上角数量徽标，点开展开成
    // 宫格画册。展开态点视频设为主视频、可单独「应用到画布」/ 下载。
    const albumRootRef = useRef<HTMLDivElement | null>(null);
    const albumPointerDownPosRef = useRef<{ x: number; y: number } | null>(null);
    const [albumExpanded, setAlbumExpanded] = useState(false);
    // 本次会话内"应到条数"——未完成的在画册里占位。存模块级登记表而非组件
    // state：onlyRenderVisibleElements 下平移出视口会卸载组件，state 会丢。
    const albumPendingTotal = useAlbumPendingTotal(id);
    const albumUrls = useMemo(() => {
      const raw = data.generationBatch;
      if (!Array.isArray(raw)) return [];
      return raw.filter((u): u is string => typeof u === 'string' && u.length > 0);
    }, [data.generationBatch]);
    const albumTotalSlots = Math.max(albumUrls.length, albumPendingTotal);
    const albumPendingCount = Math.max(0, albumPendingTotal - albumUrls.length);
    const hasAlbum = albumTotalSlots > 1;

    // 画册展开期间注册为本节点的 activeOverlay：外部 action 工具条 / 替换素材
    // 把手 / + 派生按钮都认它让位（拖动重新选中也压得住）。
    useEffect(() => {
      if (!albumExpanded) return;
      setActiveOverlayNodeId(id);
      return () => {
        if (useCanvasStore.getState().activeOverlayNodeId === id) {
          setActiveOverlayNodeId(null);
        }
      };
    }, [albumExpanded, id, setActiveOverlayNodeId]);

    useEffect(() => {
      if (!albumExpanded) return;
      const handlePointerDown = (event: PointerEvent) => {
        if (albumRootRef.current?.contains(event.target as Node)) return;
        setAlbumExpanded(false);
      };
      const handleKeyDown = (event: KeyboardEvent) => {
        if (event.key === 'Escape') setAlbumExpanded(false);
      };
      window.addEventListener('pointerdown', handlePointerDown);
      window.addEventListener('keydown', handleKeyDown);
      return () => {
        window.removeEventListener('pointerdown', handlePointerDown);
        window.removeEventListener('keydown', handleKeyDown);
      };
    }, [albumExpanded]);

    const handleSetAlbumMainVideo = useCallback(
      (url: string) => {
        updateNodeData(id, { videoUrl: url, sourceFileName: null });
        setAlbumExpanded(false);
      },
      [id, updateNodeData],
    );

    // 展开画册时取消节点激活态；必须经 onNodesChange 清 React Flow 自身的
    // selected 标志（只清 store 的 selectedNodeId 会被选中同步 effect 写回）。
    // 副作用放在 setState updater 外面：updater 必须纯（StrictMode 会双调用）。
    const handleToggleAlbumExpanded = useCallback(() => {
      if (!albumExpanded) {
        const store = useCanvasStore.getState();
        const selectionChanges = store.nodes
          .filter((node) => node.selected)
          .map((node) => ({ id: node.id, type: 'select' as const, selected: false }));
        if (selectionChanges.length > 0) {
          store.onNodesChange(selectionChanges);
        }
        setSelectedNode(null);
        // 每次展开重置「应用到画布」的落点游标。
        albumAppliedCountRef.current = 0;
      }
      setAlbumExpanded(!albumExpanded);
    }, [albumExpanded, setSelectedNode]);

    // 「应用到画布」：把这条视频作为独立视频节点放到展开宫格右侧。连续应用
    // 的落点逐次错开，避免精确叠在同一坐标上只看得见最后一个。
    const albumAppliedCountRef = useRef(0);
    const handleApplyAlbumVideoToCanvas = useCallback(
      (url: string) => {
        const self = useCanvasStore.getState().nodes.find((n) => n.id === id);
        if (!self) return;
        const applyIndex = albumAppliedCountRef.current;
        albumAppliedCountRef.current += 1;
        const position = {
          x: self.position.x + resolvedWidth * 2 + 12 + 48 + applyIndex * 36,
          y: self.position.y + applyIndex * 36,
        };
        const newNodeId = addNode(CANVAS_NODE_TYPES.video, position, {
          videoUrl: url,
          aspectRatio: data.aspectRatio,
          user_spawned: true,
        } as Partial<VideoNodeData>);
        setSelectedNode(newNodeId);
      },
      [addNode, data.aspectRatio, id, resolvedWidth, setSelectedNode],
    );

    const handleDownloadAlbumVideo = useCallback(
      async (url: string, index: number) => {
        try {
          await downloadUrlAsFile(resolveImageDisplayUrl(url), `video-gen-${id}-${index + 1}.mp4`);
        } catch (error) {
          console.error('[video-node] album download failed', error);
        }
      },
      [id],
    );

    const clearTransientPreview = useCallback(() => {
      if (transientUrlRef.current) {
        URL.revokeObjectURL(transientUrlRef.current);
        transientUrlRef.current = null;
      }
      setTransientPreviewUrl(null);
    }, []);

    const processFile = useCallback(
      async (file: File) => {
        if (!isVideoFile(file)) return;
        // 缺 project 时连本地预览都不建（同原实现的前置早退），避免闪一下又撤掉。
        if (!readUrl().project) {
          console.error("[video-node] no project in URL");
          return;
        }
        clearTransientPreview();
        const previewUrl = URL.createObjectURL(file);
        transientUrlRef.current = previewUrl;
        setTransientPreviewUrl(previewUrl);
        // 转码 + 上传 + 回写走 application/videoReplaceUpload（故事板详情「替换视频」
        // 同源）；本地 objectURL 预览是节点特有的，留在这里。
        const result = await replaceNodeVideo(id, file, {
          onTranscodedPreview: (prepared) => {
            // 源编码在本浏览器可能根本解不了（Edge+HEVC），本地预览也换成转码产物。
            clearTransientPreview();
            const preparedUrl = URL.createObjectURL(prepared);
            transientUrlRef.current = preparedUrl;
            setTransientPreviewUrl(preparedUrl);
          },
        });
        if (!result.url) clearTransientPreview();
      },
      [clearTransientPreview, id],
    );

    const handleFileChange = useCallback(
      async (event: ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (file) await processFile(file);
        event.target.value = "";
      },
      [processFile],
    );

    const handleDrop = useCallback(
      async (event: DragEvent<HTMLElement>) => {
        event.preventDefault();
        event.stopPropagation();
        const file = resolveDroppedVideoFile(event);
        if (file) await processFile(file);
      },
      [processFile],
    );

    const handleDragOver = useCallback((event: DragEvent<HTMLElement>) => {
      event.preventDefault();
      event.stopPropagation();
    }, []);


    const handleUploadClick = useCallback(() => {
      inputRef.current?.click();
    }, []);

    // Spawn the frame source node(s) to the left of this video node and wire
    // them as inputs. Used by the empty-state "首帧/首尾帧 生成视频" CTAs.
    // 首帧走图片节点（可上传也可直接生图）+ 全能参考；首尾帧仍走上传节点 + 关键帧。
    const spawnFrameUploads = useCallback(
      (mode: "firstFrame" | "firstLastFrame") => {
        const state = useCanvasStore.getState();
        const self = state.nodes.find((n) => n.id === id);
        if (!self) return;
        const isFirstFrame = mode === "firstFrame";
        // 两种源节点的默认尺寸不同（图片节点 580×360 / 上传节点 320×350），
        // 左列的定位与避让都得按实际尺寸算，否则图片节点会压到视频节点身上。
        const FRAME_WIDTH = isFirstFrame ? IMAGE_GEN_NODE_WIDTH : 320;
        const FRAME_HEIGHT = isFirstFrame ? IMAGE_GEN_NODE_HEIGHT : 350;
        const GAP_X = 40;
        const GAP_Y = 24;
        const baseX = self.position.x - FRAME_WIDTH - GAP_X;
        const stepY = FRAME_HEIGHT + GAP_Y;
        const nodeSize = (node: CanvasNode) => ({
          width:
            node.measured?.width ??
            (typeof node.width === "number" ? node.width : FRAME_WIDTH),
          height:
            node.measured?.height ??
            (typeof node.height === "number" ? node.height : FRAME_HEIGHT),
        });
        const overlaps = (
          a: { x: number; y: number; width: number; height: number },
          b: { x: number; y: number; width: number; height: number },
        ) => {
          const margin = 12;
          return (
            a.x < b.x + b.width + margin &&
            a.x + a.width + margin > b.x &&
            a.y < b.y + b.height + margin &&
            a.y + a.height + margin > b.y
          );
        };
        const occupiedRects = state.nodes
          .filter((node) => node.id !== self.id)
          .map((node) => {
            const size = nodeSize(node);
            return {
              x: node.position.x,
              y: node.position.y,
              width: size.width,
              height: size.height,
            };
          });
        const upstreamIds = new Set(
          state.edges.filter((edge) => edge.target === id).map((edge) => edge.source),
        );
        const frameColumnNodes = state.nodes.filter((node) => {
          if (!upstreamIds.has(node.id)) return false;
          if (
            node.type !== CANVAS_NODE_TYPES.upload &&
            node.type !== CANVAS_NODE_TYPES.imageGen
          ) {
            return false;
          }
          return Math.abs(node.position.x - baseX) < 8;
        });
        const lastFrameColumnY = frameColumnNodes.reduce<number | null>(
          (maxY, node) => (maxY === null ? node.position.y : Math.max(maxY, node.position.y)),
          null,
        );
        const resolveAvailableY = (preferredY: number) => {
          let y =
            lastFrameColumnY === null
              ? preferredY
              : Math.max(preferredY, lastFrameColumnY + stepY);
          for (let attempt = 0; attempt < 40; attempt += 1) {
            const candidate = { x: baseX, y, width: FRAME_WIDTH, height: FRAME_HEIGHT };
            if (!occupiedRects.some((rect) => overlaps(candidate, rect))) {
              occupiedRects.push(candidate);
              return y;
            }
            y += stepY;
          }
          occupiedRects.push({ x: baseX, y, width: FRAME_WIDTH, height: FRAME_HEIGHT });
          return y;
        };
        if (isFirstFrame) {
          const baseY = resolveAvailableY(
            self.position.y + ((self.height ?? DEFAULT_HEIGHT) - FRAME_HEIGHT) / 2,
          );
          const newId = addNode(
            CANVAS_NODE_TYPES.imageGen,
            { x: baseX, y: baseY },
            {
              displayName: "首帧",
            },
          );
          addEdge(newId, id);
          state.autoGroupSpawn(id, [newId], { label: '首帧生成视频组' });
          // 首帧走全能参考（把上游图当参考图喂给全能生成端点），并把提示词直接
          // 写好；用户已经写过提示词就别覆盖他的内容。
          updateNodeData(id, {
            genMode: "allReference",
            ...(prompt.trim() ? {} : { prompt: FIRST_FRAME_PROMPT }),
          });
          return;
        }
        const totalH = FRAME_HEIGHT * 2 + GAP_Y;
        const startY =
          self.position.y + ((self.height ?? DEFAULT_HEIGHT) - totalH) / 2;
        const firstY = resolveAvailableY(startY);
        const lastY = resolveAvailableY(firstY + stepY);
        const firstId = addNode(
          CANVAS_NODE_TYPES.upload,
          { x: baseX, y: firstY },
          { displayName: "首帧" },
        );
        addEdge(firstId, id);
        const lastId = addNode(
          CANVAS_NODE_TYPES.upload,
          { x: baseX, y: lastY },
          { displayName: "尾帧" },
        );
        addEdge(lastId, id);
        state.autoGroupSpawn(id, [firstId, lastId], { label: '首尾帧生成视频组' });
        updateNodeData(id, { genMode: "firstLastFrame" });
      },
      [addEdge, addNode, id, prompt, updateNodeData],
    );

    // Spawn reference nodes from selected asset-library entries — one per
    // selection, stacked vertically to the left of this video node, then wired
    // as upstream references so they show up in the operations panel. 编排本身
    // 只碰 canvasStore，已抽到 shared/assetLibraryReferenceSpawn 与故事板详情共用。
    const spawnCharacterLibraryReferences = useCallback(
      (selections: ReadonlyArray<AssetLibrarySelection>) => {
        spawnVideoAssetLibraryReferences(id, selections);
      },
      [id],
    );

    useEffect(() => {
      return canvasEventBus.subscribe("video-node/reupload", ({ nodeId }) => {
        if (nodeId !== id) return;
        inputRef.current?.click();
      });
    }, [id]);

    useEffect(() => {
      return canvasEventBus.subscribe(
        "video-node/external-file",
        ({ nodeId, file }) => {
          if (nodeId !== id || !isVideoFile(file)) return;
          void processFile(file);
        },
      );
    }, [id, processFile]);

    useEffect(
      () => () => {
        clearTransientPreview();
      },
      [clearTransientPreview],
    );

    const videoSource = useMemo(() => {
      if (data.videoUrl) return resolveImageDisplayUrl(data.videoUrl);
      if (transientPreviewUrl) return transientPreviewUrl;
      return null;
    }, [data.videoUrl, transientPreviewUrl]);

    // 预览专用 src：preload="metadata" 不会绘制任何一帧，又没有 poster，画布上
    // 就是一个纯黑框（视频本身正常，下载可看）。追加 `#t=0.1` 媒体片段，让浏览器
    // seek 到 0.1s 并把那一帧画出来当封面——与 NodeGenerationHistory /
    // CanvasHistoryAssetsModal 的缩略图用法一致。仅用于显示，不影响下载/抓帧/播放。
    const videoPosterSource = useMemo(() => {
      if (!videoSource) return null;
      return videoSource.includes("#t=") ? videoSource : `${videoSource}#t=0.1`;
    }, [videoSource]);

    useEffect(() => {
      updateNodeInternals(id);
    }, [id, resolvedHeight, resolvedWidth, updateNodeInternals]);

    const [hasMetadata, setHasMetadata] = useState(false);
    const [videoLoadError, setVideoLoadError] = useState(false);
    useEffect(() => {
      setHasMetadata(false);
      setVideoLoadError(false);
    }, [videoSource]);

    // ---- subtitle erase mode (libtv-style 智能去字幕) ------------------------
    const subtitleEraseMode = data.subtitleEraseMode ?? null;
    const subtitleEraseBox = data.subtitleEraseBox ?? null;
    const [isErasing, setIsErasing] = useState(false);
    // Transient drag state — null when not currently dragging.
    const [eraseDrag, setEraseDrag] = useState<{
      x0: number;
      y0: number;
      x1: number;
      y1: number;
    } | null>(null);

    /**
     * Compute the displayed video frame rect inside its container (object-contain).
     * Returns container-pixel coords. We use this to (a) size the box overlay so
     * it sits on top of the actual video pixels (not the letterbox bars) and (b)
     * convert pointer coords ↔ normalized 0..1 source coords.
     */
    const getDisplayedVideoRect = useCallback(
      (containerW: number, containerH: number) =>
        computeDisplayedVideoRect(containerW, containerH, data.widthPx, data.heightPx),
      [data.heightPx, data.widthPx],
    );

    const handleEraseExit = useCallback(() => {
      updateNodeData(id, { subtitleEraseMode: null, subtitleEraseBox: null });
      setEraseDrag(null);
    }, [id, updateNodeData]);

    const handleClipSubmit = useCallback(
      async (startMs: number, endMs: number) => {
        if (isComposingClip) return;
        const sourceUrl = data.videoUrl;
        if (!sourceUrl) return;
        if (endMs <= startMs) return;
        setIsComposingClip(true);
        setClipError(null);
        try {
          // 提交核心在 application/videoClipSubmit（故事板详情「剪辑轨道」共用）。
          const result = await submitVideoClip(id, {
            sourceUrl,
            startMs,
            endMs,
            quality,
          });
          if (result.nodeId) {
            updateNodeData(id, {
              isClipMode: false,
              clipStartMs: null,
              clipEndMs: null,
            });
          }
          if (result.error) setClipError(result.error);
        } finally {
          setIsComposingClip(false);
        }
      },
      [data.videoUrl, id, isComposingClip, quality, updateNodeData],
    );

    const handleEraseSubmit = useCallback(async () => {
      if (isErasing) return;
      if (!data.videoUrl) return;
      if (subtitleEraseMode === "box" && !subtitleEraseBox) return;
      const projectId = readUrl().project;
      if (!projectId) {
        console.error("[video-node] no project in URL");
        return {};
      }
      setIsErasing(true);
      try {
        // 提交核心在 application/videoSubtitleErase（故事板详情「智能去字幕」共用）。
        const result = await runVideoSubtitleErase(projectId, {
          sourceUrl: data.videoUrl,
          mode: subtitleEraseMode === "box" ? "box" : "smart_subtitle",
          box: subtitleEraseMode === "box" ? subtitleEraseBox : null,
        });
        if (result.url) {
          updateNodeData(id, {
            videoUrl: result.url,
            subtitleEraseMode: null,
            subtitleEraseBox: null,
          });
        } else {
          console.warn("[video-node] erase completed without url", result);
        }
      } catch (error) {
        console.error("[video-node] subtitle erase failed", error);
      } finally {
        setIsErasing(false);
      }
    }, [
      data.videoUrl,
      id,
      isErasing,
      subtitleEraseBox,
      subtitleEraseMode,
      updateNodeData,
    ]);


    useEffect(() => {
      return subscribeNodeAction(({ nodeId, action, executionMode, requestId }) => {
        if (nodeId !== id || action !== "generate_video") return;
        publishNodeActionAccepted(requestId, id, action);
        void handleSubmit()
          .then((output) => {
            const latest = useCanvasStore.getState().nodes.find((node) => node.id === id);
            const latestVideoUrl = isVideoNode(latest) && typeof latest.data.videoUrl === "string"
              ? latest.data.videoUrl
              : undefined;
            publishNodeActionSuccess(requestId, id, action, {
              ...(output.videoUrl ? { videoUrl: output.videoUrl } : {}),
              ...(latestVideoUrl ? { videoUrl: latestVideoUrl } : {}),
              ...(executionMode === "single" ? { submitted: true } : {}),
            });
          })
          .catch((error) => publishNodeActionError(requestId, id, action, error));
      });
    }, [handleSubmit, id]);

    const hasMainlineContext = hasMainlineContexts(
      (data as { mainline_context?: unknown }).mainline_context,
    );

    const cardToneClass = canvasNodeFrameClass({
      selected,
      mainline: hasMainlineContext,
    });

    const isUploading = Boolean(data.isUploading);
    const isEmptyVideoBody = !videoSource && !isUploading && !isGenerating && !hasGenerationError;
    const bodySurfaceClass = isEmptyVideoBody
      ? CANVAS_NODE_INPUT_SURFACE_CLASS
      : CANVAS_NODE_PANEL_SURFACE_CLASS;
    const bodyFrameClass = isEmptyVideoBody
      ? selected
        ? CANVAS_NODE_INPUT_BODY_SELECTED_FRAME_CLASS
        : CANVAS_NODE_INPUT_BODY_FRAME_CLASS
      : cardToneClass;
    const showVideoOpsPanel =
      selected &&
      !isBoxSelecting &&
      !albumExpanded &&
      !isClipMode &&
      !subtitleEraseMode &&
      !data.referenceOnly &&
      // 视频高清节点用自己的 VideoUpscaleEditorOverlay 配置面板，不走常规生成面板。
      !data.isUpscaleNode;

    const handleCaptureFrame = useCallback(
      async (mode: "first" | "last" | "current") => {
        if (isCapturingFrame) return;
        if (!data.videoUrl) return;
        const liveEl = videoRef.current;
        const seekSec = resolveCaptureSeekSec(mode, {
          currentTimeSec: liveEl?.currentTime ?? null,
          durationSec:
            liveEl && Number.isFinite(liveEl.duration) ? liveEl.duration : null,
          fallbackDurationSec:
            typeof data.durationMs === "number" ? data.durationMs / 1000 : null,
        });
        const titleKey =
          mode === "first"
            ? "node.videoNode.frame.titleFirst"
            : mode === "last"
              ? "node.videoNode.frame.titleLast"
              : "node.videoNode.frame.titleCurrent";

        setIsCapturingFrame(true);
        try {
          // 抽帧 + 上传 + 建节点走 application/videoCaptureFrame（故事板详情「截帧」同源）。
          await captureVideoFrameToNode(id, {
            videoUrl: data.videoUrl,
            seekSec,
            displayName: t(titleKey),
          });
        } finally {
          setIsCapturingFrame(false);
        }
      },
      [data.durationMs, data.videoUrl, id, isCapturingFrame, t],
    );

    return (
      <div
        ref={albumRootRef}
        className="group relative h-full w-full overflow-visible"
        style={{ width: resolvedWidth, height: resolvedHeight }}
        onClick={() => setSelectedNode(id)}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
      >
        {/* 叠卡画册的卡片边：从主视频右侧探出（与图片节点同款），点卡边也能展开画册。 */}
        {hasAlbum && !albumExpanded && videoSource && (
          <>
            {Array.from({ length: Math.min(albumTotalSlots - 1, 3) }, (_, index) => {
              const step = index + 1;
              return (
                <div
                  key={`album-deck-${index}`}
                  role="button"
                  tabIndex={-1}
                  title="展开画册"
                  onClick={(event) => {
                    event.stopPropagation();
                    handleToggleAlbumExpanded();
                  }}
                  className="absolute cursor-pointer rounded-[var(--node-radius)] border border-white/[0.18] bg-gradient-to-b from-[#48484d] to-[#2d2d31] shadow-[0_4px_14px_rgba(0,0,0,0.4)]"
                  style={{
                    top: step * 7,
                    bottom: step * 7,
                    left: step * 6,
                    right: -step * 7,
                    transform: `rotate(${step * 1.1}deg)`,
                    transformOrigin: 'center right',
                    opacity: 1 - step * 0.18,
                  }}
                />
              );
            })}
          </>
        )}
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

        {/* 画册展开时隐藏浮动标题和分辨率角标——画册容器自带头部（与图片节点一致）。 */}
        {!albumExpanded && (
          <>
            <NodeHeader
              className={NODE_HEADER_FLOATING_POSITION_CLASS}
              icon={<VideoIcon className="h-4 w-4" />}
              titleText={resolvedTitle}
              editable
              onTitleChange={(nextTitle) =>
                updateNodeData(id, { displayName: nextTitle })
              }
            />
            {videoSource &&
            hasMetadata &&
            !videoLoadError &&
            typeof data.widthPx === "number" &&
            typeof data.heightPx === "number" &&
            data.widthPx > 0 &&
            data.heightPx > 0 ? (
              <div
                className="absolute -top-7 right-1 z-20 flex items-center gap-1 rounded-md border border-white/10 bg-black/55 px-2 py-0.5 text-[11px] font-medium tabular-nums text-white/70 backdrop-blur-sm"
                title={t("node.videoNode.resolution")}
              >
                <VideoIcon className="h-3 w-3 text-white/45" />
                {data.widthPx}×{data.heightPx}
              </div>
            ) : null}
          </>
        )}
        <NodeContextBadges
          contexts={(data as { mainline_context?: unknown }).mainline_context}
        />

        <NodeResizeHandle
          minWidth={MIN_WIDTH}
          minHeight={MIN_HEIGHT}
          maxWidth={MAX_WIDTH}
          maxHeight={MAX_HEIGHT}
          keepAspectRatio
        />

        {!videoSource && !isUploading && !isGenerating && !data.isUpscaleNode && (
          <NodeSideActionRail nodeId={id} autoHide selected={Boolean(selected)}>
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                handleUploadClick();
              }}
              className={NODE_SIDE_ACTION_BUTTON_CLASS}
              title={t("node.videoNode.clickToUpload")}
            >
              <UploadIcon className={NODE_SIDE_ACTION_ICON_CLASS} />
              <span>{t("node.videoNode.upload")}</span>
            </button>
          </NodeSideActionRail>
        )}

        <div
          className={`relative flex h-full w-full items-center justify-center ${videoSource ? "overflow-hidden" : "overflow-visible"} rounded-[var(--node-radius)] border ${bodySurfaceClass} transition-colors ${bodyFrameClass} ${
            // 画册展开时藏起节点本体——半透明的画册容器盖不严，底下的视频会透出来。
            albumExpanded && hasAlbum ? "invisible" : ""
          }`}
        >
          {/* 生成/上传中优先显示 loading：原地重新生成时 videoUrl 仍是上一条结果，
              若不加这层 guard，旧视频会一直占位、isGenerating 分支永远到不了。
              失败时 isGenerating 归 false，旧视频自动复现（videoUrl 未被清空）。 */}
          {!isGenerating && !isUploading && videoSource ? (
            <video
              ref={setVideoRef}
              src={videoPosterSource ?? undefined}
              className="h-full w-full object-contain"
              playsInline
              preload="metadata"
              onClick={() => {
                // 点击视频本体只负责选中节点 —— 播放/暂停统一交给左下角按钮。
                setSelectedNode(id);
              }}
              onLoadedMetadata={(event) => {
                const el = event.currentTarget;
                setHasMetadata(true);
                setVideoLoadError(false);
                if (el.videoWidth && el.videoHeight) {
                  // 只把视频真实像素记到 widthPx/heightPx；不要写回 aspectRatio。
                  // aspectRatio 仅保存用户选的比例预设（16:9 / auto…），否则
                  // chip 会显示成像素串(1248:704)，且会作为非法 aspect_ratio 带进
                  // 下一次生成请求。
                  const updates: Partial<VideoNodeData> = {};
                  if (data.widthPx !== el.videoWidth)
                    updates.widthPx = el.videoWidth;
                  if (data.heightPx !== el.videoHeight)
                    updates.heightPx = el.videoHeight;
                  if (data.durationMs !== Math.round(el.duration * 1000)) {
                    updates.durationMs = Math.round(el.duration * 1000);
                  }
                  if (Object.keys(updates).length > 0) {
                    updateNodeData(id, updates);
                  }
                }
              }}
              onError={() => {
                setHasMetadata(true);
                setVideoLoadError(true);
              }}
            />
          ) : isUploading ? (
            <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-text-muted/85">
              <Loader2 className="h-7 w-7 animate-spin opacity-70" />
              <span className="px-4 text-center text-[12px] leading-6">
                {t("node.videoNode.uploading")}
              </span>
            </div>
          ) : isGenerating && historyPreviewUrl ? (
            // 生成进行中，但用户点了历史记录预览：临时播放那条历史视频，新视频
            // 仍在后台生成。顶部 pill 提示「生成中」，右上「返回」回到 loading。
            <div className="relative h-full w-full">
              <video
                src={resolveImageDisplayUrl(historyPreviewUrl)}
                className="h-full w-full object-contain"
                controls
                playsInline
                preload="metadata"
                onClick={(event) => event.stopPropagation()}
              />
              <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between gap-2 p-2">
                <span className="pointer-events-auto inline-flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-[11px] text-white/90 backdrop-blur">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  新视频生成中…
                </span>
                <button
                  type="button"
                  className="nodrag pointer-events-auto inline-flex items-center gap-1 rounded-full bg-black/60 px-2.5 py-1 text-[11px] text-white/90 backdrop-blur transition-colors hover:bg-black/75"
                  onClick={(event) => {
                    event.stopPropagation();
                    setHistoryPreviewUrl(null);
                  }}
                >
                  <XIcon className="h-3 w-3" />
                  返回
                </button>
              </div>
            </div>
          ) : isGenerating ? (
            <div className="relative h-full w-full">
              {data.previewImageUrl ? (
                <img
                  src={resolveImageDisplayUrl(data.previewImageUrl)}
                  alt=""
                  className="h-full w-full object-contain"
                  draggable={false}
                />
              ) : null}
              <NodeGenerationOverlay
                startedAt={data.generationStartedAt ?? null}
                durationMs={data.generationDurationMs}
                hasBackground={Boolean(data.previewImageUrl)}
              />
            </div>
          ) : hasGenerationError ? (
            <div className="flex h-full w-full flex-col items-center justify-center gap-2 px-4 text-red-300">
              <AlertTriangle className="h-7 w-7 opacity-90" />
              <span className="text-center text-[12px] font-medium leading-5 text-red-200">
                视频生成失败
              </span>
              <span className="max-h-[64px] overflow-y-auto break-words text-center text-[11px] leading-5 text-red-200/90 [overflow-wrap:anywhere]">
                {generationError}
              </span>
              {generationErrorRequestId && (
                <div className="flex w-full max-w-[240px] items-center gap-1 rounded bg-red-500/10 px-2 py-1">
                  <span className="shrink-0 text-[10px] text-red-300/70">请求ID</span>
                  <code
                    className="min-w-0 flex-1 truncate font-mono text-[10px] text-red-200"
                    title={generationErrorRequestId}
                  >
                    {generationErrorRequestId}
                  </code>
                </div>
              )}
              <div className="mt-1">
                <RegenerateButton
                  onClick={() => void handleSubmit()}
                  busy={isGenerating}
                  disabled={submitDisabled}
                />
              </div>
            </div>
          ) : data.isUpscaleNode ? (
            <div className="flex h-full w-full items-center justify-center px-6">
              <span className="text-center text-sm font-medium text-text-dark/78">
                {t("node.videoUpscale.placeholder")}
              </span>
            </div>
          ) : isConnected ? (
            // 已连线：不再显示文字 CTA，只在节点中间放一个图标（对齐 libtv）。
            <div className="flex h-full w-full items-center justify-center">
              <Play className="h-9 w-9 text-text-muted/46" />
            </div>
          ) : (
            <div className="flex h-full w-full items-center px-8">
              {/* 上游含视频时只能走全能参考，首尾帧/首帧这两个 CTA 会引导到被禁用的
                  firstLastFrame 模式，所以此时隐藏。 */}
              {upstreamCounts.videos === 0 && (
                <div className="flex min-h-0 flex-col justify-center gap-2 py-4">
                  <div className="text-xs text-[var(--canvas-node-input-helper)]">试试：</div>
                  <div className="flex flex-col gap-0.5">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        spawnFrameUploads("firstLastFrame");
                      }}
                      className="nodrag -mx-2 inline-flex items-center gap-3 rounded-lg px-2 py-2 text-sm text-text-dark transition-colors hover:bg-white/[0.08]"
                    >
                      <Layers className="h-4 w-4 text-text-muted/90" />
                      <span>首尾帧生成视频</span>
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        spawnFrameUploads("firstFrame");
                      }}
                      className="nodrag -mx-2 inline-flex items-center gap-3 rounded-lg px-2 py-2 text-sm text-text-dark transition-colors hover:bg-white/[0.08]"
                    >
                      <Sparkles className="h-4 w-4 text-text-muted/90" />
                      <span>首帧生成视频</span>
                    </button>
                  </div>
                </div>
              )}
              <Play className="ml-auto mr-20 h-9 w-9 text-text-muted/46" />
            </div>
          )}

          {videoSource && videoLoadError && !isGenerating && !isUploading && (
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-2 bg-bg-dark/70 px-4 text-center text-red-200">
              <AlertTriangle className="h-6 w-6 text-red-300" />
              <span className="text-[12px] font-medium">视频加载失败</span>
            </div>
          )}

          {videoSource && !hasMetadata && !isUploading && !isGenerating && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-bg-dark/40">
              <Loader2 className="h-6 w-6 animate-spin text-text-muted/70" />
            </div>
          )}

          {videoSource &&
            hasMetadata &&
            !videoLoadError &&
            !isGenerating &&
            !isUploading &&
            !subtitleEraseMode && (
              <VideoPlayerControls
                videoEl={videoEl}
                isCapturingFrame={isCapturingFrame}
                onCapture={handleCaptureFrame}
              />
            )}

          {/* 画册数量徽标：hover 节点出现，hover 徽标箭头下探，点击展开画册。 */}
          {hasAlbum && !isGenerating && videoSource && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                handleToggleAlbumExpanded();
              }}
              onPointerDown={(event) => event.stopPropagation()}
              title={`展开 ${albumTotalSlots} 条生成结果`}
              className="nodrag group/albumpill absolute right-2 top-2 z-10 hidden items-center gap-1 rounded-full bg-black/65 px-2.5 py-1 text-[12px] font-medium tabular-nums text-white shadow-lg backdrop-blur-sm transition-colors hover:bg-black/85 group-hover:inline-flex"
            >
              {albumPendingCount > 0
                ? `${albumUrls.length}/${albumPendingTotal}`
                : albumUrls.length}
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform duration-200 ${
                  albumExpanded
                    ? 'rotate-180 group-hover/albumpill:-translate-y-[2px]'
                    : 'group-hover/albumpill:translate-y-[2px]'
                }`}
              />
            </button>
          )}

          {videoSource && subtitleEraseMode === "box" && (
            <SubtitleEraseBoxOverlay
              box={subtitleEraseBox}
              drag={eraseDrag}
              disabled={isErasing}
              getDisplayedRect={getDisplayedVideoRect}
              onDragStart={(start) => setEraseDrag(start)}
              onDragMove={(next) =>
                setEraseDrag((prev) =>
                  prev ? { ...prev, x1: next.x1, y1: next.y1 } : prev,
                )
              }
              onDragEnd={(final) => {
                setEraseDrag(null);
                if (!final) return;
                updateNodeData(id, { subtitleEraseBox: final });
              }}
            />
          )}
        </div>

        {/* 展开的画册宫格：与图片节点同构——「组」式轮廓 + 2 列宫格；点视频设为
            主视频并收拢；hover 出现「应用到画布」+ 下载；按住可拖动整个节点。 */}
        {albumExpanded && hasAlbum && (
          <div
            className="nowheel absolute -left-3 -top-3 z-[80] cursor-grab rounded-2xl border border-white/15 bg-white/[0.045] p-3 shadow-[0_16px_48px_rgba(0,0,0,0.4)] backdrop-blur-[2px] active:cursor-grabbing"
            style={{ width: resolvedWidth * 2 + 12 + 24 }}
            onClick={(event) => event.stopPropagation()}
            onPointerDownCapture={(event) => {
              albumPointerDownPosRef.current = { x: event.clientX, y: event.clientY };
            }}
          >
            <div className="mb-2 flex items-center gap-1.5 px-1 text-[12px] font-medium text-white/60">
              <VideoIcon className="h-3.5 w-3.5 text-white/45" />
              画册 · {albumTotalSlots} 条
            </div>
            <div className="grid grid-cols-2 gap-3">
              {albumUrls.map((url, index) => {
                const isMain = url === data.videoUrl;
                return (
                  <div
                    key={`album-cell-${index}`}
                    role="button"
                    tabIndex={-1}
                    title="点击设为主视频"
                    onClick={(event) => {
                      event.stopPropagation();
                      // 拖动画册（移动节点）后松手补发的 click 不算选主视频。
                      const start = albumPointerDownPosRef.current;
                      if (
                        start
                        && Math.hypot(event.clientX - start.x, event.clientY - start.y) > 5
                      ) {
                        return;
                      }
                      handleSetAlbumMainVideo(url);
                    }}
                    className={`group/albumcell relative cursor-pointer overflow-hidden rounded-[var(--node-radius)] border bg-[#1b1b1d] shadow-[0_12px_32px_rgba(0,0,0,0.45)] transition-colors ${
                      isMain
                        ? 'border-accent/80 ring-2 ring-accent/40'
                        : 'border-white/12 hover:border-white/35'
                    }`}
                    style={{ width: resolvedWidth, height: resolvedHeight }}
                  >
                    <video
                      src={resolveImageDisplayUrl(url)}
                      muted
                      playsInline
                      preload="metadata"
                      className="h-full w-full object-cover"
                      onMouseEnter={(event) => {
                        void event.currentTarget.play().catch(() => undefined);
                      }}
                      onMouseLeave={(event) => {
                        event.currentTarget.pause();
                        event.currentTarget.currentTime = 0;
                      }}
                    />
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        handleApplyAlbumVideoToCanvas(url);
                      }}
                      title="把这条视频作为独立视频节点放到画布上"
                      className="nodrag absolute left-2 top-2 z-10 hidden h-7 items-center gap-1 rounded-md bg-black/70 px-2.5 text-[12px] font-medium text-white backdrop-blur-sm transition-colors hover:bg-black/90 group-hover/albumcell:inline-flex"
                    >
                      <UploadIcon className="h-3.5 w-3.5" />
                      应用到画布
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleDownloadAlbumVideo(url, index);
                      }}
                      title="下载这条视频"
                      className="nodrag absolute right-2 top-2 z-10 hidden h-7 w-7 items-center justify-center rounded-full bg-black/70 text-white backdrop-blur-sm transition-colors hover:bg-black/90 group-hover/albumcell:inline-flex"
                    >
                      <Download className="h-3.5 w-3.5" />
                    </button>
                    {isMain && (
                      <span className="absolute bottom-2 left-2 z-10 rounded-md bg-black/65 px-2 py-0.5 text-[11px] font-medium text-white backdrop-blur-sm">
                        主视频
                      </span>
                    )}
                  </div>
                );
              })}
              {/* 还在生成中的槽位：占位骨架，完成一条替换一条。 */}
              {Array.from({ length: albumPendingCount }, (_, index) => (
                <div
                  key={`album-pending-${index}`}
                  className="relative flex items-center justify-center overflow-hidden rounded-[var(--node-radius)] border border-white/10 bg-[#1b1b1d] shadow-[0_12px_32px_rgba(0,0,0,0.45)]"
                  style={{ width: resolvedWidth, height: resolvedHeight }}
                >
                  <div className="flex flex-col items-center gap-2 text-text-muted/70">
                    <Loader2 className="h-6 w-6 animate-spin" />
                    <span className="text-[12px]">生成中…</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {isClipMode && videoSource && (
          <div
            className="absolute left-0 right-0 z-10 flex flex-col gap-1"
            style={{ top: `calc(100% + ${OPERATIONS_PANEL_GAP}px)` }}
          >
            <VideoClipPanel
              videoUrl={videoSource}
              durationMs={durationMs}
              clipStartMs={clipStartMs}
              clipEndMs={clipEndMs}
              isSubmitting={isComposingClip}
              onChange={(patch) => updateNodeData(id, patch)}
              onExit={() => {
                if (isComposingClip) return;
                setClipError(null);
                updateNodeData(id, { isClipMode: false });
              }}
              onSubmit={(start, end) => {
                void handleClipSubmit(start, end);
              }}
            />
            {clipError && (
              <div className="rounded-md bg-red-500/15 px-3 py-1.5 text-[11px] text-red-300 break-words [overflow-wrap:anywhere]">
                剪辑失败：{clipError}
              </div>
            )}
          </div>
        )}

        {showVideoOpsPanel && (
            <OperationPanelShell
              expanded={panelExpanded}
              onCollapse={() => setPanelExpanded(false)}
              inlineClassName={`nodrag absolute z-30 flex flex-col rounded-[var(--node-radius)] ${CANVAS_NODE_OPS_PANEL_CLASS}`}
              inlineStyle={{
                top: `calc(100% + ${OPERATIONS_PANEL_GAP}px)`,
                left: -panelOverhang,
                right: -panelOverhang,
                height: panelHeight,
              }}
              modalStyle={{
                width: `min(${OPERATIONS_PANEL_EXPANDED_WIDTH}px, 92vw)`,
                height: `min(${OPERATIONS_PANEL_EXPANDED_HEIGHT}px, 86vh)`,
              }}
            >
              <PanelExpandButton
                expanded={panelExpanded}
                onToggle={() => setPanelExpanded((v) => !v)}
                className="absolute right-2 top-2 z-20"
              />
              {/* 表单的全部数据/回调都来自 useVideoGenerationForm；节点只补上
                  「打开资产库」这一个属于宿主自己的浮层编排。 */}
              <VideoGenerationForm
                {...videoFormProps}
                onOpenCharacterLibrary={openCharacterLibrary}
              />
            </OperationPanelShell>
          )}

        {selected &&
          !isBoxSelecting &&
          !albumExpanded &&
          !isClipMode &&
          !subtitleEraseMode &&
          !data.referenceOnly &&
          hasCompletedHistoryRecords(historyRecords) && (
            <div
              className={`nodrag absolute z-[300] rounded-[var(--node-radius)] ${CANVAS_NODE_OPS_PANEL_CLASS} ${NODE_OPS_PANEL_ENTER_CLASS} px-3 py-2`}
              style={{
                top: `calc(100% + ${OPERATIONS_PANEL_GAP * 2 + panelHeight}px)`,
                left: -panelOverhang,
                right: -panelOverhang,
              }}
              onClick={(event) => event.stopPropagation()}
            >
              <NodeGenerationHistory
                records={historyRecords}
                isLoading={historyLoading}
                onRestore={handleRestoreHistory}
                onRefresh={() => void refreshHistory()}
                isActive={(record) => {
                  const url = historyRecordOutputUrl(record);
                  if (!url) return false;
                  // 预览态下高亮正在预览的历史条，否则高亮当前主视频。
                  if (isGenerating && historyPreviewUrl) {
                    return url === historyPreviewUrl;
                  }
                  return url === data.videoUrl;
                }}
              />
            </div>
          )}

        {subtitleEraseMode && (
          <div
            className="nodrag absolute left-0 right-0 z-10 flex justify-center"
            style={{ top: `calc(100% + ${OPERATIONS_PANEL_GAP}px)` }}
            onClick={(event) => event.stopPropagation()}
          >
            <SubtitleEraseOpsPanel
              mode={subtitleEraseMode}
              isErasing={isErasing}
              hasBox={!!subtitleEraseBox}
              onExit={handleEraseExit}
              onResetBox={() => updateNodeData(id, { subtitleEraseBox: null })}
              onSubmit={handleEraseSubmit}
            />
          </div>
        )}

        <input
          ref={inputRef}
          type="file"
          accept={VIDEO_FILE_ACCEPT}
          className="hidden"
          onChange={handleFileChange}
        />

        <AssetLibraryModal
          open={isCharacterLibraryOpen}
          project={readUrl().project ?? null}
          onClose={() => setIsCharacterLibraryOpen(false)}
          onConfirm={(selections) =>
            spawnCharacterLibraryReferences(selections)
          }
        />
      </div>
    );
  },
);

VideoNode.displayName = "VideoNode";

// --- custom video player controls ------------------------------------------ //
//
// 替代 <video controls>：libtv 风格的浮层（底部一条）。订阅原生 <video>
// 的 play/pause/timeupdate/durationchange/volumechange，写回时直接操作元素，
// 由事件驱动 state 单向同步。隐藏时机：默认显示 0.85 透明度 + hover 加深，
// 不做自动隐藏，避免画布上看不到「这个视频还能控制」。

interface VideoPlayerControlsProps {
  videoEl: HTMLVideoElement | null;
  isCapturingFrame: boolean;
  onCapture: (mode: "first" | "last" | "current") => void;
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function VideoPlayerControls({
  videoEl,
  isCapturingFrame,
  onCapture,
}: VideoPlayerControlsProps) {
  const { t } = useTranslation();
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const [isHoveringFrame, setIsHoveringFrame] = useState(false);

  useEffect(() => {
    if (!videoEl) return;
    const syncAll = () => {
      setIsPlaying(!videoEl.paused);
      setCurrentTime(videoEl.currentTime);
      setDuration(Number.isFinite(videoEl.duration) ? videoEl.duration : 0);
      setIsMuted(videoEl.muted);
    };
    syncAll();
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onTime = () => setCurrentTime(videoEl.currentTime);
    const onDur = () => {
      setDuration(Number.isFinite(videoEl.duration) ? videoEl.duration : 0);
    };
    const onVol = () => setIsMuted(videoEl.muted);
    videoEl.addEventListener("play", onPlay);
    videoEl.addEventListener("pause", onPause);
    videoEl.addEventListener("timeupdate", onTime);
    videoEl.addEventListener("durationchange", onDur);
    videoEl.addEventListener("loadedmetadata", onDur);
    videoEl.addEventListener("volumechange", onVol);
    return () => {
      videoEl.removeEventListener("play", onPlay);
      videoEl.removeEventListener("pause", onPause);
      videoEl.removeEventListener("timeupdate", onTime);
      videoEl.removeEventListener("durationchange", onDur);
      videoEl.removeEventListener("loadedmetadata", onDur);
      videoEl.removeEventListener("volumechange", onVol);
    };
  }, [videoEl]);

  const togglePlay = useCallback(() => {
    if (!videoEl) return;
    if (videoEl.paused) {
      void videoEl.play().catch(() => undefined);
    } else {
      videoEl.pause();
    }
  }, [videoEl]);

  const toggleMute = useCallback(() => {
    if (!videoEl) return;
    videoEl.muted = !videoEl.muted;
  }, [videoEl]);

  const onSeek = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      if (!videoEl) return;
      const next = Number(event.target.value);
      if (!Number.isFinite(next)) return;
      videoEl.currentTime = next;
      setCurrentTime(next);
    },
    [videoEl],
  );

  // 进度百分比（用作 range 背景的渐变锚点）。
  const progressPct =
    duration > 0 ? Math.min(100, (currentTime / duration) * 100) : 0;
  const sliderBg = `linear-gradient(to right, rgb(var(--accent-rgb)) 0%, rgb(var(--accent-rgb)) ${progressPct}%, rgba(255,255,255,0.18) ${progressPct}%, rgba(255,255,255,0.18) 100%)`;

  return (
    <div className="nodrag absolute inset-x-0 bottom-0 z-20 flex items-center gap-2.5 bg-gradient-to-t from-black/75 via-black/45 to-transparent px-3 pb-2 pt-6 text-text-dark">
      <button
        type="button"
        onClick={(event) => {
          // 唯一的播放/暂停入口:阻止冒泡,避免点它时把节点也选中。
          event.stopPropagation();
          togglePlay();
        }}
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-text-dark/90 transition-colors hover:bg-white/[0.12] hover:text-text-dark"
        title={
          isPlaying
            ? t("node.videoNode.player.pause", { defaultValue: "暂停" })
            : t("node.videoNode.player.play", { defaultValue: "播放" })
        }
      >
        {isPlaying ? (
          <Pause className="h-4 w-4" />
        ) : (
          <Play className="h-4 w-4" fill="currentColor" />
        )}
      </button>

      <span className="shrink-0 text-[11px] tabular-nums text-text-dark/85">
        {formatTime(currentTime)}
      </span>

      <input
        type="range"
        min={0}
        max={duration > 0 ? duration : 0}
        step={0.05}
        value={currentTime}
        onChange={onSeek}
        onMouseDown={(event) => event.stopPropagation()}
        className="video-player-scrubber h-1 min-w-0 flex-1 cursor-pointer appearance-none rounded-full"
        style={{ background: sliderBg }}
      />

      <span className="shrink-0 text-[11px] tabular-nums text-text-dark/85">
        {formatTime(duration)}
      </span>

      <button
        type="button"
        onClick={toggleMute}
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-text-dark/90 transition-colors hover:bg-white/[0.12] hover:text-text-dark"
        title={
          isMuted
            ? t("node.videoNode.player.unmute", { defaultValue: "取消静音" })
            : t("node.videoNode.player.mute", { defaultValue: "静音" })
        }
      >
        {isMuted ? (
          <VolumeX className="h-4 w-4" />
        ) : (
          <Volume2 className="h-4 w-4" />
        )}
      </button>

      <div
        className="relative shrink-0"
        onMouseEnter={() => setIsHoveringFrame(true)}
        onMouseLeave={() => setIsHoveringFrame(false)}
      >
        <button
          type="button"
          disabled={isCapturingFrame}
          onClick={() => onCapture("current")}
          title={t("node.videoNode.frame.captureCurrent")}
          className={`inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors ${
            isCapturingFrame
              ? "cursor-not-allowed text-text-muted/60"
              : "text-text-dark/90 hover:bg-white/[0.12] hover:text-text-dark"
          }`}
        >
          {isCapturingFrame ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Camera className="h-4 w-4" />
          )}
        </button>

        {isHoveringFrame && !isCapturingFrame && (
          <div className="absolute bottom-full right-0 flex flex-col gap-1 rounded-lg border border-white/10 bg-surface-dark/95 p-1 text-xs shadow-2xl backdrop-blur-md">
            <button
              type="button"
              onClick={() => onCapture("first")}
              className="whitespace-nowrap rounded-md px-3 py-1.5 text-left text-text-dark transition-colors hover:bg-white/[0.08]"
            >
              {t("node.videoNode.frame.captureFirst")}
            </button>
            <button
              type="button"
              onClick={() => onCapture("last")}
              className="whitespace-nowrap rounded-md px-3 py-1.5 text-left text-text-dark transition-colors hover:bg-white/[0.08]"
            >
              {t("node.videoNode.frame.captureLast")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// --- subtitle erase: box overlay ------------------------------------------- //

// --- subtitle erase: ops panel --------------------------------------------- //

interface SubtitleEraseOpsPanelProps {
  mode: "smart" | "box";
  isErasing: boolean;
  hasBox: boolean;
  onExit: () => void;
  onResetBox: () => void;
  onSubmit: () => void;
}

function SubtitleEraseOpsPanel({
  mode,
  isErasing,
  hasBox,
  onExit,
  onResetBox,
  onSubmit,
}: SubtitleEraseOpsPanelProps) {
  const { t } = useTranslation();
  const submitDisabled = isErasing || (mode === "box" && !hasBox);
  const labelKey =
    mode === "box"
      ? "nodeToolbar.video.subtitleRemovalBox"
      : "nodeToolbar.video.subtitleRemovalSmart";
  const icon =
    mode === "box" ? (
      <Square className="h-3.5 w-3.5 shrink-0 text-text-muted" />
    ) : (
      <Sparkles className="h-3.5 w-3.5 shrink-0 text-text-muted" />
    );

  return (
    <div className={`flex min-w-[420px] max-w-[calc(100vw-32px)] items-center gap-2 ${CANVAS_NODE_TOOLBAR_PILL_CLASS}`}>
      <button
        type="button"
        onClick={onExit}
        title={t("node.videoNode.subtitleErase.exit")}
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-bg-dark/70 text-text-muted transition-colors hover:bg-bg-dark hover:text-text-dark"
      >
        <XIcon className="h-4 w-4" />
      </button>

      <div className="flex min-w-0 flex-1 items-center gap-1.5 px-2 text-xs text-text-dark">
        {icon}
        <span className="truncate font-medium">{t(labelKey)}</span>
      </div>

      {mode === "box" && (
        <button
          type="button"
          onClick={onResetBox}
          title={t("node.videoNode.subtitleErase.tools.reset")}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded px-1 text-text-dark/72 transition-colors hover:text-text-dark"
        >
          <RotateCcw className="h-4 w-4" />
        </button>
      )}

      <CreditCostPill
        display="0"
        disabled={submitDisabled}
        className={NODE_CREDIT_PILL_FLAT_CLASS}
      />

      <button
        type="button"
        disabled={submitDisabled}
        onClick={onSubmit}
        title={t("node.videoNode.subtitleErase.submit")}
        className={`${NODE_GENERATE_BUTTON_BASE_CLASS} shrink-0 ${
          submitDisabled
            ? NODE_GENERATE_BUTTON_DISABLED_CLASS
            : NODE_GENERATE_BUTTON_ENABLED_CLASS
        }`}
      >
        {isErasing ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <ArrowUp className="h-4 w-4" />
        )}
      </button>
    </div>
  );
}
