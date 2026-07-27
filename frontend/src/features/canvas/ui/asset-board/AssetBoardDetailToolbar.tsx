// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
  type ReactElement,
  type RefObject,
} from 'react';
import {
  ChevronDown,
  ChevronRight,
  Crop,
  Download,
  Eraser,
  FastForward,
  Film,
  Grid2x2,
  Grid3x3,
  History,
  ImageUpscale,
  Languages,
  LayoutDashboard,
  LayoutGrid,
  Loader2,
  MoreHorizontal,
  Mountain,
  Package,
  PenLine,
  RefreshCw,
  Rewind,
  Scissors,
  Shapes,
  Star,
  User,
  Users,
  Wand2,
  X,
  type LucideIcon,
} from 'lucide-react';

import type { FreezoneGenerationHistoryRecord } from '@/api/ops';
import type {
  FreezoneVideoUpscaleDenoise,
  FreezoneVideoUpscaleResolution,
} from '@/api/ops';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/shadcn/dropdown-menu';
import { spawnAssetBoardImageOpNode } from '@/features/canvas/application/assetBoardImageOps';
import { canvasEventBus } from '@/features/canvas/application/canvasServices';
import { type GridActionKey } from '@/features/canvas/application/gridTemplateAction';
import { resolveImageDisplayUrl } from '@/features/canvas/application/imageData';
import { matteImage } from '@/features/canvas/application/matteImage';
import {
  canRegenerateExportImageNode,
  regenerateExportImageNode,
} from '@/features/canvas/application/regenerateExportNode';
import { translateNodeText } from '@/features/canvas/application/translateText';
import { runVideoSubtitleErase } from '@/features/canvas/application/videoSubtitleErase';
import {
  createVideoUpscaleResultNode,
  submitVideoUpscale,
  VIDEO_UPSCALE_DENOISE_OPTIONS,
  VIDEO_UPSCALE_RESOLUTIONS,
  VIDEO_UPSCALE_RESOLUTION_LABEL,
} from '@/features/canvas/application/videoUpscale';
import {
  CANVAS_NODE_TYPES,
  NODE_TOOL_TYPES,
  isAudioNode,
  isImageEditNode,
  isVideoComposeNode,
  isVideoNode,
  resolveNodeSourceImageUrl,
  type CanvasNode,
  type CanvasNodeData,
  type NodeToolType,
} from '@/features/canvas/domain/canvasNodes';
import {
  KEY_ELEMENT_CATEGORY_KEYS,
  KEY_ELEMENT_CATEGORY_LABEL,
  readKeyElementCategory,
  type KeyElementCategory,
} from '@/features/canvas/domain/keyElements';
import { useNodeGenerationHistory } from '@/features/canvas/hooks/useNodeGenerationHistory';
import { getNodeToolPlugins } from '@/features/canvas/tools';
import {
  NodeGenerationHistory,
  hasCompletedHistoryRecords,
  historyRecordOutputUrl,
} from '@/features/canvas/ui/NodeGenerationHistory';
import { AssetBoardImageOps } from './AssetBoardImageEditMenu';
import { AssetBoardVideoOps } from './AssetBoardVideoOpsMenu';
import {
  DetailToolbarButton,
  DETAIL_TOOLBAR_BUTTON_CLASS,
} from './AssetBoardToolbarButton';
import { VideoComposeModal } from '@/features/canvas/compose/VideoComposeModal';
import type { ComposeTimelineState } from '@/features/canvas/compose/timelineModel';
import { downloadUrlAsFile } from '@/lib/browserDownload';
import { readUrl } from '@/lib/url-params';
import { useCanvasStore } from '@/stores/canvasStore';

// 按钮组件本体在 AssetBoardToolbarButton（打断与 AssetBoardImageEditMenu 的循环
// import）；这里再导出一次，保持既有 import 路径（文本/视频工具条等）不变。
export { DetailToolbarButton };

// 「...」更多菜单的项样式（面板 rounded-lg、项 hover bg-white/5，与本分支体系一致）。
const MORE_MENU_ITEM_CLASS =
  'flex w-full items-center gap-2 rounded-[6px] px-2.5 py-1.5 text-left text-[12px] text-white/80 transition-colors hover:bg-white/5 hover:text-white disabled:cursor-not-allowed disabled:opacity-45';

/** 「...」更多菜单里的叶子动作项（抠图/裁剪/标注/分格抽取/历史）。 */
interface MoreMenuAction {
  kind: 'action';
  key: string;
  icon: LucideIcon;
  label: string;
  /** 进行中：图标换 spinner 并禁用（与工具条按钮同款反馈，如抠图在途）。 */
  busy?: boolean;
  /** 处于「已展开/已激活」态（如历史列表打开时高亮该项）。 */
  active?: boolean;
  onSelect: () => void;
}

/** 「...」更多菜单里的展开型子菜单项（宫格模板：点/悬停展开 9 个模板）。 */
interface MoreMenuSubmenu {
  kind: 'submenu';
  key: string;
  icon: LucideIcon;
  label: string;
  /** 有在途提交时展示的替代文案（如「多机位九宫格」）；非空即显示 spinner。 */
  pendingLabel?: string | null;
  disabled?: boolean;
  children: Array<{
    key: string;
    icon: LucideIcon;
    label: string;
    /** 右侧灰字（如「14 算力」）。 */
    hint?: string;
    onSelect: () => void;
  }>;
}

export type MoreMenuEntry = MoreMenuAction | MoreMenuSubmenu;

const MORE_MENU_CLOSE_DELAY_MS = 140;

/** 关键元素分类图标（设置关键元素子菜单用）。 */
const KEY_ELEMENT_CATEGORY_ICON: Record<KeyElementCategory, LucideIcon> = {
  character: User,
  scene: Mountain,
  object: Package,
  other: Shapes,
};

/**
 * 「设置关键元素」子菜单项：把本节点标记为关键元素并归类（人物/场景/物品/其他）
 * 或取消。标记只写节点 data.keyElementCategory（见 domain/keyElements），故事板
 * 顶部关键元素栏据此常驻。图片工具条的「...」与视频详情头部的「...」共用这一份，
 * 保证两处的文案、当前态标记与取消项完全一致。
 */
export function keyElementMenuEntry(
  node: CanvasNode,
  updateNodeData: (nodeId: string, patch: Partial<CanvasNodeData>) => void,
): MoreMenuSubmenu {
  const current = readKeyElementCategory(node.data as Record<string, unknown>);
  return {
    kind: 'submenu',
    key: 'keyElement',
    icon: Star,
    label: current ? `关键元素 · ${KEY_ELEMENT_CATEGORY_LABEL[current]}` : '设置关键元素',
    children: [
      ...KEY_ELEMENT_CATEGORY_KEYS.map((category) => ({
        key: `key-${category}`,
        icon: KEY_ELEMENT_CATEGORY_ICON[category],
        label: KEY_ELEMENT_CATEGORY_LABEL[category],
        hint: current === category ? '当前' : undefined,
        onSelect: () =>
          updateNodeData(node.id, { keyElementCategory: category } as Partial<CanvasNodeData>),
      })),
      ...(current
        ? [
            {
              key: 'key-clear',
              icon: X,
              label: '取消关键元素',
              onSelect: () =>
                updateNodeData(node.id, { keyElementCategory: null } as Partial<CanvasNodeData>),
            },
          ]
        : []),
    ],
  };
}

/**
 * 图片详情工具条的「...」更多菜单：把抠图/裁剪/标注/分格抽取/历史 从常显按钮收进一个
 * 悬停展开的下拉面板（入口与动作与原来完全等价，只是从常显移进菜单）。宫格模板不在此列
 * ——它已挪回常显工具条做独立下拉按钮（用户要求）。
 *
 * - hover 为主：移入图标或面板都保持打开，移出延迟 {@link MORE_MENU_CLOSE_DELAY_MS}ms
 *   收起（防抖，避免掠过即闪）；点击图标也可切换开关。
 * - 键盘可达：focus 落到触发器/任一项即展开（onFocus 冒泡），焦点整体离开则收起，
 *   Esc 收起并把焦点还给触发器。
 * - 面板绝对定位于触发器下方、右对齐，z-50 高于详情正文；样式对齐本分支体系。
 * - 叶子项点击后不主动关闭（悬停菜单惯例：移开/Esc 才收），保证连续操作与在途反馈可见；
 *   历史点击仍切换下方历史列表。仍保留 submenu 渲染分支（通用能力），当前无条目使用。
 */
export function DetailMoreMenu({
  entries,
  triggerClassName,
  triggerLabel = '更多',
}: {
  entries: MoreMenuEntry[];
  /** 触发器样式：默认工具条按钮；详情头部那颗传 header 图标按钮的类。 */
  triggerClassName?: string;
  /**
   * 触发器的可及名称。图片详情里头部与工具条各有一颗「...」（前者是节点操作、
   * 后者是素材操作），叫同一个名字会让读屏与测试都分不清，所以头部那颗传
   * 「节点操作」。
   */
  triggerLabel?: string;
}): ReactElement {
  const [open, setOpen] = useState(false);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  const clearCloseTimer = useCallback(() => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);
  const openNow = useCallback(() => {
    clearCloseTimer();
    setOpen(true);
  }, [clearCloseTimer]);
  const closeNow = useCallback(() => {
    clearCloseTimer();
    setOpen(false);
    setExpandedKey(null);
  }, [clearCloseTimer]);
  const scheduleClose = useCallback(() => {
    clearCloseTimer();
    closeTimerRef.current = setTimeout(() => {
      setOpen(false);
      setExpandedKey(null);
    }, MORE_MENU_CLOSE_DELAY_MS);
  }, [clearCloseTimer]);
  // 卸载时清掉未触发的收起定时器（详情按 key={node.id} 整体重挂载会走这里）。
  useEffect(() => clearCloseTimer, [clearCloseTimer]);

  const handleBlur = useCallback(
    (event: FocusEvent<HTMLDivElement>) => {
      // 焦点整体离开菜单（下一焦点不在 wrapper 内）→ 收起，不抢焦点。
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
        closeNow();
      }
    },
    [closeNow],
  );

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'Escape' && open) {
        event.stopPropagation();
        closeNow();
        triggerRef.current?.focus();
      }
    },
    [closeNow, open],
  );

  return (
    <div
      className="relative inline-flex"
      onMouseEnter={openNow}
      onMouseLeave={scheduleClose}
      onFocus={openNow}
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
    >
      <button
        ref={triggerRef}
        type="button"
        aria-label={triggerLabel}
        aria-haspopup="true"
        aria-expanded={open}
        title={triggerLabel}
        onClick={() => (open ? closeNow() : openNow())}
        className={triggerClassName ?? DETAIL_TOOLBAR_BUTTON_CLASS}
      >
        <MoreHorizontal className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div
          aria-label="更多操作"
          className="absolute right-0 top-full z-50 mt-1.5 min-w-[210px] rounded-lg border border-white/10 bg-[#2e2e2e] p-1 text-white/85 shadow-xl"
        >
          {entries.map((entry) => {
            if (entry.kind === 'submenu') {
              const Icon = entry.icon;
              const expanded = expandedKey === entry.key;
              const pending = Boolean(entry.pendingLabel);
              return (
                <div key={entry.key} onMouseEnter={() => !entry.disabled && setExpandedKey(entry.key)}>
                  <button
                    type="button"
                    aria-haspopup="true"
                    aria-expanded={expanded}
                    disabled={entry.disabled}
                    onClick={() => setExpandedKey((current) => (current === entry.key ? null : entry.key))}
                    className={MORE_MENU_ITEM_CLASS}
                  >
                    {pending ? (
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                    ) : (
                      <Icon className="h-4 w-4 shrink-0" />
                    )}
                    <span className="flex-1">{entry.pendingLabel ?? entry.label}</span>
                    <ChevronRight
                      className={`h-3.5 w-3.5 shrink-0 text-white/40 transition-transform ${expanded ? 'rotate-90' : ''}`}
                    />
                  </button>
                  {expanded && (
                    <div className="mt-0.5 space-y-0.5 border-l border-white/10 pl-2">
                      {entry.children.map((child) => {
                        const ChildIcon = child.icon;
                        return (
                          <button
                            key={child.key}
                            type="button"
                            onClick={child.onSelect}
                            className={MORE_MENU_ITEM_CLASS}
                          >
                            <ChildIcon className="h-4 w-4 shrink-0" />
                            <span className="flex-1">{child.label}</span>
                            {child.hint && (
                              <span className="text-[10px] text-white/40">{child.hint}</span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            }
            const Icon = entry.icon;
            return (
              <button
                key={entry.key}
                type="button"
                disabled={entry.busy}
                onClick={entry.onSelect}
                className={`${MORE_MENU_ITEM_CLASS} ${entry.active ? 'bg-white/[0.06] text-white' : ''}`}
              >
                {entry.busy ? (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                ) : (
                  <Icon className="h-4 w-4 shrink-0" />
                )}
                <span className="flex-1">{entry.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/**
 * 折叠的「历史」区：查看 + 恢复的最简列表（复用工作流节点内的 NodeGenerationHistory
 * 条）。restore 语义由宿主注入（图片/视频回填字段不同）；生成中禁恢复（节点内是
 * 非破坏性预览，详情本批直接禁用，避免误覆写在途结果）。
 */
function DetailHistorySection({
  nodeId,
  restoreDisabled,
  onRestore,
}: {
  nodeId: string;
  restoreDisabled: boolean;
  onRestore: (record: FreezoneGenerationHistoryRecord) => void;
}): ReactElement {
  const { records, isLoading, refresh } = useNodeGenerationHistory(nodeId);
  const handleRestore = useCallback(
    (record: FreezoneGenerationHistoryRecord) => {
      if (restoreDisabled) return;
      onRestore(record);
    },
    [onRestore, restoreDisabled],
  );
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
      <NodeGenerationHistory
        records={records}
        isLoading={isLoading}
        onRestore={handleRestore}
        onRefresh={() => void refresh()}
        disabled={restoreDisabled}
      />
      {!isLoading && !hasCompletedHistoryRecords(records) && (
        <p className="py-1 text-[12px] text-white/40">暂无生成历史</p>
      )}
    </div>
  );
}

// 宫格模板清单（与 NodeActionToolbar.gridActions 同源：label 即 zh 翻译值，提交时
// label 同时作为展示 prompt 下发——真正的模板由 key→mode 映射决定）。
// 这里不挂算力：点一项只是**建节点**，不花钱；价钱在新节点的 ↑ 按钮上按当前
// 模型/参数活价显示（AssetBoardImageGenForm），在这儿标价反而像是点了就扣。
const GRID_ACTION_DEFS: Array<{
  key: GridActionKey;
  icon: typeof Crop;
  label: string;
}> = [
  { key: 'multiCameraGrid', icon: Grid3x3, label: '多机位九宫格' },
  { key: 'plotFourGrid', icon: Grid2x2, label: '剧情推演四宫格' },
  { key: 'faceThreeView', icon: User, label: '角色脸部三视图' },
  { key: 'productThreeView', icon: Package, label: '产品三视图' },
  { key: 'serialStoryboard25', icon: LayoutDashboard, label: '25宫格连贯分镜' },
  { key: 'cinematicLightCorrection', icon: Film, label: '电影级光影校正' },
  { key: 'characterThreeView', icon: Users, label: '角色三视图生成' },
  { key: 'sceneSettingSheet', icon: Mountain, label: '场景设定图' },
  { key: 'frameProjection3sLater', icon: FastForward, label: '画面推演 - 3秒后' },
  { key: 'frameProjection5sEarlier', icon: Rewind, label: '画面推演 - 5秒前' },
];

/**
 * 图片详情工具条。常显：下载 / 失败重试 / 编辑下拉 / 全景 / 多角度 / 重打光 / 宫格模板；
 * 抠图 / 裁剪 / 标注 / 分格抽取 / 历史 收进「...」更多菜单（悬停展开）。
 *
 * @param onOpenNode 建出新节点后把详情切过去（同头部「创建副本」那条路径）。
 *   宫格模板现在是「先建节点、按 ↑ 才提交」，不切详情用户就看不出发生了什么。
 */
export function AssetBoardImageDetailToolbar({
  node,
  onOpenNode,
}: {
  node: CanvasNode;
  onOpenNode?: (nodeId: string) => void;
}): ReactElement {
  const updateNodeData = useCanvasStore((state) => state.updateNodeData);
  const data = node.data as Record<string, unknown>;
  const imageSource = useMemo(() => resolveNodeSourceImageUrl(node), [node]);
  const tools = useMemo(() => getNodeToolPlugins(node), [node]);
  const isImageEdit = isImageEditNode(node);
  const isGenerating = data.isGenerating === true;
  const canRegenerate = canRegenerateExportImageNode(data);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isMatting, setIsMatting] = useState(false);

  const hasTool = useCallback(
    (type: NodeToolType) => tools.some((tool) => tool.type === type),
    [tools],
  );

  // 文件名推断沿用 NodeActionToolbar.resolveImageDownloadFilename 的规则。
  const handleDownload = useCallback(async () => {
    if (!imageSource || isDownloading) return;
    const sourceFileName =
      typeof data.sourceFileName === 'string' ? data.sourceFileName.trim() : '';
    const displayName = typeof data.displayName === 'string' ? data.displayName.trim() : '';
    const filename = sourceFileName || (displayName ? `${displayName}.png` : `node-${node.id}.png`);
    setIsDownloading(true);
    try {
      await downloadUrlAsFile(resolveImageDisplayUrl(imageSource), filename);
    } catch (error) {
      console.error('[asset-board] image download failed', error);
    } finally {
      setIsDownloading(false);
    }
  }, [data.displayName, data.sourceFileName, imageSource, isDownloading, node.id]);

  const openToolDialog = useCallback(
    (toolType: NodeToolType) => {
      // NodeToolDialog 全局挂载在保活的 Canvas 树里（Canvas.tsx），故事板模式下
      // 事件仍会被消费；crop/annotate/split 三类均走 portal 到 body 的 z-[300]
      // 弹窗，高于故事板 z-30。
      canvasEventBus.publish('tool-dialog/open', { nodeId: node.id, toolType });
    },
    [node.id],
  );

  // 进行中反馈：结果虽落在新建的画布节点上，触发按钮也要有 busy 态——
  // 用 matteImage 返回的后台链 completion 收口（settle 后恢复可点）。
  const handleMatte = useCallback(() => {
    if (!imageSource || isMatting) return;
    const result = matteImage(node.id, imageSource, { displayName: '抠图' });
    if (!result) return;
    setIsMatting(true);
    // 低成本视口预定位（M7）：结果节点已同步建好，立即让保活挂载的 Canvas 把
    // 视口对准它——即便画布当前 suspended（故事板可见），pendingFocusNodeId 的
    // 消费 effect 不受 suspended 门控，用户切回工作流时视口已就位。
    useCanvasStore.getState().requestFocusNode(result.nodeId);
    void result.completion.finally(() => setIsMatting(false));
  }, [imageSource, isMatting, node.id]);

  // 点功能 = **先建节点、不提交**（对标 liblib）：在下游建一个空的图片生成节点，
  // 节点名 = 功能名，输入框里带一枚可关可切的功能 chip；详情随即切到新节点，
  // 用户改完提示词/参考图/比例（或在功能框里换个功能）按 ↑ 才真正提交。
  //
  // 这条只改故事板的交互形态：工作流侧的「确认即提交」（GridActionConfirmOverlay
  // + submitGridTemplateAction）一行没动，能力完全一样。
  const handleGridAction = useCallback(
    (def: (typeof GRID_ACTION_DEFS)[number]) => {
      if (!imageSource) return;
      const newNodeId = spawnAssetBoardImageOpNode(node.id, imageSource, def.key);
      if (!newNodeId) return;
      // 低成本视口预定位（M7）：保活挂载的 Canvas 先把视口对准新节点，用户切回
      // 工作流时不用自己找。
      useCanvasStore.getState().requestFocusNode(newNodeId);
      onOpenNode?.(newNodeId);
    },
    [imageSource, node.id, onOpenNode],
  );

  const handleRestoreHistory = useCallback(
    (record: FreezoneGenerationHistoryRecord) => {
      const url = historyRecordOutputUrl(record);
      if (!url) return;
      // 与 ImageGenNode 非生成态恢复同语义（生成中在 DetailHistorySection 已被禁用）。
      updateNodeData(node.id, {
        imageUrl: url,
        previewImageUrl: url,
        isGenerating: false,
        generationStartedAt: null,
        generationBatch: null,
      } as Partial<CanvasNodeData>);
    },
    [node.id, updateNodeData],
  );

  // 「...」更多菜单条目：抠图 / 裁剪 / 标注 / 分格抽取 / 宫格模板 / 历史。显隐条件与
  // 原常显按钮逐条同源（imageEdit 节点不给编辑类入口、需对应工具插件、需有图源），
  // 触发的动作也完全一致——只是入口从常显按钮移进了菜单。历史恒有（imageEdit 也有）。
  const moreEntries: MoreMenuEntry[] = [];
  if (!isImageEdit && imageSource) {
    moreEntries.push({
      kind: 'action',
      key: 'matte',
      icon: Scissors,
      label: '抠图',
      busy: isMatting,
      onSelect: handleMatte,
    });
  }
  if (!isImageEdit && hasTool(NODE_TOOL_TYPES.crop)) {
    moreEntries.push({
      kind: 'action',
      key: 'crop',
      icon: Crop,
      label: '裁剪',
      onSelect: () => openToolDialog(NODE_TOOL_TYPES.crop),
    });
  }
  if (!isImageEdit && hasTool(NODE_TOOL_TYPES.annotate)) {
    moreEntries.push({
      kind: 'action',
      key: 'annotate',
      icon: PenLine,
      label: '标注',
      onSelect: () => openToolDialog(NODE_TOOL_TYPES.annotate),
    });
  }
  if (!isImageEdit && hasTool(NODE_TOOL_TYPES.splitStoryboard)) {
    moreEntries.push({
      kind: 'action',
      key: 'split',
      icon: Grid3x3,
      label: '分格抽取',
      onSelect: () => openToolDialog(NODE_TOOL_TYPES.splitStoryboard),
    });
  }
  // 宫格模板已挪到常显工具条（独立下拉按钮，见下方 return），不再进「...」菜单。

  // 「设置关键元素」不在这条工具条里——它是节点级操作，已统一挪到详情头部那颗
  // 「...」（四栏一致，见 AssetBoardDetail）。这里只留与图片素材本身相关的操作。

  moreEntries.push({
    kind: 'action',
    key: 'history',
    icon: History,
    label: '历史',
    active: historyOpen,
    onSelect: () => setHistoryOpen((open) => !open),
  });

  return (
    <div className="flex flex-col gap-2">
      {/* 居中：工具条是详情的操作行，媒体本身也是居中的，左对齐会让这行孤零零
          吊在左上角（用户要求）。 */}
      <div className="flex flex-wrap items-center justify-center gap-1.5">
        <DetailToolbarButton
          icon={Download}
          label="下载"
          busy={isDownloading}
          disabled={!imageSource}
          onClick={() => void handleDownload()}
        />
        {canRegenerate && (
          <DetailToolbarButton
            icon={RefreshCw}
            label="重新生成"
            busy={isGenerating}
            title="重新提交这次生成（失败重试）"
            onClick={() => void regenerateExportImageNode(node.id)}
          />
        )}
        {/* 常显第二批图片操作（编辑下拉：重绘/擦除/高清/扩图/旋转 + 全景/多角度/重打光）。
            按钮落在本行，展开的平面配置行用 w-full 自动换到下一行。显隐与工作流
            NodeActionToolbar 同源：imageEdit 节点不给图片编辑入口，无图源不显示。 */}
        {!isImageEdit && imageSource && (
          <AssetBoardImageOps node={node} imageSource={imageSource} />
        )}
        {/* 宫格模板：常显下拉按钮（从「...」菜单挪出来，用户要求）。点开列 9 个模板，
            选中即在下游建一个同名的空图片节点并把详情切过去——不再当场提交，
            用户在新节点的输入框里确认（或换功能）后按 ↑ 才真正生成。 */}
        {!isImageEdit && imageSource && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                title="基于本图套用宫格 / 多视图模板生成"
                className={DETAIL_TOOLBAR_BUTTON_CLASS}
              >
                <LayoutGrid className="h-3.5 w-3.5" />
                宫格模板
                <ChevronDown className="h-3 w-3" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="start"
              sideOffset={6}
              className="z-50 min-w-[200px] border-white/10 bg-[#2e2e2e] text-white/85 shadow-xl"
            >
              {GRID_ACTION_DEFS.map((def) => {
                const Icon = def.icon;
                return (
                  <DropdownMenuItem
                    key={def.key}
                    className="gap-2 rounded-[6px] text-white/80 focus:bg-white/[0.08] focus:text-white"
                    onSelect={() => handleGridAction(def)}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className="flex-1">{def.label}</span>
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        {/* 「...」更多菜单：抠图/裁剪/标注/分格抽取/历史（悬停展开，见组件注释）。 */}
        <DetailMoreMenu entries={moreEntries} />
      </div>
      {historyOpen && (
        <DetailHistorySection
          nodeId={node.id}
          restoreDisabled={isGenerating}
          onRestore={handleRestoreHistory}
        />
      )}
    </div>
  );
}

/** 节点片源：videoUrl 优先，其次高清/去字幕等写回的 resultVideoUrl。 */
function videoSourceUrlOf(node: CanvasNode): string | null {
  const data = node.data as Record<string, unknown>;
  if (typeof data.videoUrl === 'string' && data.videoUrl) return data.videoUrl;
  if (typeof data.resultVideoUrl === 'string' && data.resultVideoUrl) return data.resultVideoUrl;
  return null;
}

/** 生成失败过的节点：没产物但「历史」里可能存着上一次成功的结果，工具条得留着。 */
function hasFailedGeneration(node: CanvasNode): boolean {
  const data = node.data as Record<string, unknown>;
  return typeof data.generationError === 'string' && data.generationError.trim().length > 0;
}

/**
 * 图片详情工具条有没有可用操作。没有就别渲染整条——空节点（还没出图）上的
 * 下载/编辑/宫格全要图源，摆一排灰按钮只是噪音（用户要求）。
 * 两个例外：
 * - 导出图节点生成失败时没图源，但「重新生成」正是这时候要点的；
 * - 生成失败的节点没图源，可「历史」（在「...」菜单里，本身不要求图源）是用户
 *   回到上一次成功结果的唯一入口，整条藏掉等于把恢复路径也藏了。
 */
export function hasImageDetailActions(node: CanvasNode): boolean {
  return (
    Boolean(resolveNodeSourceImageUrl(node)) ||
    canRegenerateExportImageNode(node.data as Record<string, unknown>) ||
    hasFailedGeneration(node)
  );
}

/**
 * 视频详情工具条有没有可用操作。同上：没片源的视频节点整条不渲染。
 * 两个例外：
 * - 合成节点的「剪辑」靠的是上游素材而非自身片源，它自己还没出片也留着
 *   （素材不够时按钮自带「需要至少 2 个已就绪的上游视频素材」的说明）；
 * - 生成失败的节点片源为空，但「历史」不要求片源，是恢复上一次成功结果的唯一入口。
 */
export function hasVideoDetailActions(node: CanvasNode): boolean {
  return Boolean(videoSourceUrlOf(node)) || isVideoComposeNode(node) || hasFailedGeneration(node);
}

/**
 * 视频详情工具条：剪辑（合成时间线）/ 高清 / 智能去字幕 / 翻译提示词 / 下载 / 历史，
 * 外加第二批视频操作（剪辑轨道 / 解析 / 分离音视频 / 截帧 / 替换视频 / 框选擦除，
 * 见 AssetBoardVideoOps）。
 */
export function AssetBoardVideoDetailToolbar({
  node,
  playerRef,
}: {
  node: CanvasNode;
  /** 详情正文里那个活的 <video>：截帧的「当前帧/尾帧」要读它的进度与时长。 */
  playerRef?: RefObject<HTMLVideoElement | null>;
}): ReactElement {
  const updateNodeData = useCanvasStore((state) => state.updateNodeData);
  const data = node.data as Record<string, unknown>;
  const isVideo = isVideoNode(node);
  const isCompose = isVideoComposeNode(node);
  const videoUrl = videoSourceUrlOf(node);
  const prompt = typeof data.prompt === 'string' ? data.prompt : '';
  const isGenerating = data.isGenerating === true;

  const [historyOpen, setHistoryOpen] = useState(false);
  const [upscaleOpen, setUpscaleOpen] = useState(false);
  const [upscaleResolution, setUpscaleResolution] =
    useState<FreezoneVideoUpscaleResolution>('1080p');
  const [upscaleDenoise, setUpscaleDenoise] = useState<FreezoneVideoUpscaleDenoise>('1x');
  const [isErasing, setIsErasing] = useState(false);
  const [isTranslating, setIsTranslating] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isSubmittingUpscale, setIsSubmittingUpscale] = useState(false);
  const [composeSeeds, setComposeSeeds] = useState<string[] | null>(null);

  const project = readUrl().project;
  const canvasId = readUrl().canvas ?? 'default';

  // 视频合成入口的可用性：合成节点沿用工作流「≥2 个有片源的上游视频」门槛；
  // 普通视频节点以自身为素材种子，只要有片源即可。
  // 用响应式 selector 取代 useMemo 里的 getState() 快照 —— 后者只在依赖
  // （isCompose/node.id）变化时重算，上游视频在详情打开期间才生成完成不会
  // 触发重渲染，「剪辑」按钮会一直卡在禁用态。selector 返回 number，
  // Zustand 用 Object.is 去重，值不变不会多渲染；只订阅这一个派生值，
  // 不会因为 store 里其它无关字段变化而多渲染。
  const composeUpstreamVideoCount = useCanvasStore((state) => {
    if (!isCompose) return 0;
    const byId = new Map(state.nodes.map((candidate) => [candidate.id, candidate]));
    return state.edges
      .filter((edge) => edge.target === node.id)
      .map((edge) => byId.get(edge.source))
      .filter((upstream): upstream is CanvasNode => Boolean(upstream))
      .filter((upstream) => isVideoNode(upstream) && Boolean(upstream.data.videoUrl)).length;
  });
  const canOpenCompose = isCompose ? composeUpstreamVideoCount >= 2 : Boolean(videoUrl);

  const openCompose = useCallback(() => {
    if (!project || !canOpenCompose) return;
    if (!isCompose) {
      setComposeSeeds([node.id]);
      return;
    }
    // 与 VideoComposeNode 相同的种子推导：上游有片源的视频/音频节点按 y 排序。
    const state = useCanvasStore.getState();
    const byId = new Map(state.nodes.map((candidate) => [candidate.id, candidate]));
    const seeds = state.edges
      .filter((edge) => edge.target === node.id)
      .map((edge) => byId.get(edge.source))
      .filter((upstream): upstream is CanvasNode => Boolean(upstream))
      .filter(
        (upstream) =>
          (isVideoNode(upstream) && Boolean(upstream.data.videoUrl)) ||
          (isAudioNode(upstream) && Boolean(upstream.data.audioUrl)),
      )
      .sort((a, b) => (a.position?.y ?? 0) - (b.position?.y ?? 0))
      .map((upstream) => upstream.id);
    setComposeSeeds(seeds);
  }, [canOpenCompose, isCompose, node.id, project]);

  const handleComposed = useCallback(
    (url: string, coverUrl: string | null) => {
      // 与 VideoComposeNode.onComposed 同语义：下游建视频节点承载结果并连边；
      // 合成节点还会聚焦新节点并回写 resultVideoUrl/previewImageUrl。
      const store = useCanvasStore.getState();
      const position = store.findNodePosition(node.id, 580, 380);
      const newId = store.addNode(CANVAS_NODE_TYPES.video, position, {
        videoUrl: url,
        previewImageUrl: coverUrl,
        displayName: '合成视频',
        sourceFileName: null,
      } as Partial<CanvasNodeData>);
      store.addEdge(node.id, newId);
      if (isCompose) {
        store.setSelectedNode(newId);
        store.requestFocusNode(newId);
        store.updateNodeData(node.id, {
          resultVideoUrl: url,
          previewImageUrl: coverUrl,
        } as Partial<CanvasNodeData>);
      }
      setComposeSeeds(null);
    },
    [isCompose, node.id],
  );

  const handleDownload = useCallback(async () => {
    if (!videoUrl || isDownloading) return;
    // 文件名推断沿用 NodeActionToolbar 视频下载的规则。
    const sourceFileName =
      typeof data.sourceFileName === 'string' && data.sourceFileName.trim().length > 0
        ? data.sourceFileName
        : typeof data.displayName === 'string' && data.displayName.trim().length > 0
          ? `${data.displayName}.mp4`
          : `video-${node.id}.mp4`;
    setIsDownloading(true);
    try {
      await downloadUrlAsFile(resolveImageDisplayUrl(videoUrl), sourceFileName);
    } catch (error) {
      console.error('[asset-board] video download failed', error);
    } finally {
      setIsDownloading(false);
    }
  }, [data.displayName, data.sourceFileName, isDownloading, node.id, videoUrl]);

  const handleUpscaleSubmit = useCallback(() => {
    if (!videoUrl || isSubmittingUpscale) return;
    // 沿用工作流「先建 isUpscaleNode 结果节点」语义，配置在详情选好后直接提交。
    const displayName = `高清（${VIDEO_UPSCALE_RESOLUTION_LABEL[upscaleResolution]}）`;
    const upscaleNodeId = createVideoUpscaleResultNode(node.id, {
      sourceUrl: videoUrl,
      displayName,
      resolution: upscaleResolution,
      denoise: upscaleDenoise,
    });
    if (!upscaleNodeId) return;
    // 配置行收起后，工具条「高清」按钮转为 spinner 直到 submit settle——
    // 与翻译/去字幕/宫格的进行中反馈风格一致（结果落新建的画布节点）。
    setUpscaleOpen(false);
    setIsSubmittingUpscale(true);
    // 低成本视口预定位（M7）：结果节点已同步建好，立即对焦（见 handleMatte 注释）。
    useCanvasStore.getState().requestFocusNode(upscaleNodeId);
    void submitVideoUpscale(upscaleNodeId, {
      sourceUrl: videoUrl,
      resolution: upscaleResolution,
      denoise: upscaleDenoise,
    }).finally(() => setIsSubmittingUpscale(false));
  }, [isSubmittingUpscale, node.id, upscaleDenoise, upscaleResolution, videoUrl]);

  const handleSmartErase = useCallback(async () => {
    if (!videoUrl || isErasing) return;
    if (!project) {
      console.error('[asset-board] subtitle erase: no project in URL');
      return;
    }
    setIsErasing(true);
    try {
      const result = await runVideoSubtitleErase(project, {
        sourceUrl: videoUrl,
        mode: 'smart_subtitle',
        box: null,
      });
      if (result.url) {
        updateNodeData(node.id, { videoUrl: result.url } as Partial<CanvasNodeData>);
      } else {
        console.warn('[asset-board] subtitle erase completed without url', result);
      }
    } catch (error) {
      console.error('[asset-board] subtitle erase failed', error);
    } finally {
      setIsErasing(false);
    }
  }, [isErasing, node.id, project, updateNodeData, videoUrl]);

  const handleTranslate = useCallback(async () => {
    if (isTranslating || prompt.trim().length === 0) return;
    if (!project) {
      console.error('[asset-board] translate: no project in URL');
      return;
    }
    setIsTranslating(true);
    try {
      const translated = await translateNodeText(project, {
        text: prompt,
        nodeId: node.id,
        nodeType: 'video',
      });
      if (translated) {
        updateNodeData(node.id, { prompt: translated } as Partial<CanvasNodeData>);
      }
    } catch (error) {
      console.error('[asset-board] translate failed', error);
    } finally {
      setIsTranslating(false);
    }
  }, [isTranslating, node.id, project, prompt, updateNodeData]);

  const handleRestoreHistory = useCallback(
    (record: FreezoneGenerationHistoryRecord) => {
      const url = historyRecordOutputUrl(record);
      if (!url) return;
      // 与 VideoNode 非生成态恢复同语义。
      updateNodeData(node.id, {
        videoUrl: url,
        isGenerating: false,
        generationStartedAt: null,
        sourceFileName: null,
        generationError: null,
        generationErrorDetails: null,
        generationErrorRequestId: null,
        generationBatch: null,
      } as Partial<CanvasNodeData>);
    },
    [node.id, updateNodeData],
  );

  return (
    <div className="flex flex-col gap-2">
      {/* 居中：工具条是详情的操作行，媒体本身也是居中的，左对齐会让这行孤零零
          吊在左上角（用户要求）。 */}
      <div className="flex flex-wrap items-center justify-center gap-1.5">
        <DetailToolbarButton
          icon={Film}
          label="剪辑"
          disabled={!project || !canOpenCompose}
          title={
            isCompose && !canOpenCompose
              ? '需要至少 2 个已就绪的上游视频素材'
              : '打开视频合成时间线'
          }
          onClick={openCompose}
        />
        {isVideo && (
          <DetailToolbarButton
            icon={ImageUpscale}
            label="高清"
            busy={isSubmittingUpscale}
            disabled={!videoUrl}
            onClick={() => setUpscaleOpen((open) => !open)}
            trailing={<ChevronDown className="h-3 w-3" />}
          />
        )}
        {isVideo && (
          <DetailToolbarButton
            icon={Eraser}
            label="智能去字幕"
            busy={isErasing}
            disabled={!videoUrl}
            title="smart 档：整段智能擦除字幕，完成后替换本视频"
            onClick={() => void handleSmartErase()}
          />
        )}
        {/* 第二批视频操作（剪辑轨道 / 解析 / 分离音视频 / 截帧 / 替换视频 / 框选擦除）。
            按钮落在本行，展开的面板用 w-full 自动换到下一行。显隐与工作流
            NodeActionToolbar 的 isVideoNode 分支同源：videoCompose 节点不是视频节点，
            只保留「剪辑（合成时间线）」与下载；无片源时整组不出。 */}
        {isVideo && videoUrl && (
          <AssetBoardVideoOps node={node} videoUrl={videoUrl} playerRef={playerRef} />
        )}
        {isVideo && prompt.trim().length > 0 && (
          <DetailToolbarButton
            icon={Languages}
            label="翻译提示词"
            busy={isTranslating}
            onClick={() => void handleTranslate()}
          />
        )}
        <DetailToolbarButton
          icon={Download}
          label="下载"
          busy={isDownloading}
          disabled={!videoUrl}
          onClick={() => void handleDownload()}
        />
        {isVideo && (
          <DetailToolbarButton
            icon={History}
            label="历史"
            onClick={() => setHistoryOpen((open) => !open)}
          />
        )}
      </div>

      {upscaleOpen && isVideo && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
          <span className="text-[12px] text-white/40">分辨率</span>
          <div className="inline-flex items-center gap-0.5 rounded-md border border-white/10 bg-white/[0.04] p-0.5">
            {VIDEO_UPSCALE_RESOLUTIONS.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setUpscaleResolution(value)}
                className={`rounded px-2 py-0.5 text-[12px] transition-colors ${
                  upscaleResolution === value
                    ? 'bg-white/15 text-white'
                    : 'text-white/50 hover:bg-white/5 hover:text-white/80'
                }`}
              >
                {VIDEO_UPSCALE_RESOLUTION_LABEL[value]}
              </button>
            ))}
          </div>
          <span className="text-[12px] text-white/40">降噪</span>
          <div className="inline-flex items-center gap-0.5 rounded-md border border-white/10 bg-white/[0.04] p-0.5">
            {VIDEO_UPSCALE_DENOISE_OPTIONS.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setUpscaleDenoise(value)}
                className={`rounded px-2 py-0.5 text-[12px] transition-colors ${
                  upscaleDenoise === value
                    ? 'bg-white/15 text-white'
                    : 'text-white/50 hover:bg-white/5 hover:text-white/80'
                }`}
              >
                {value === 'none' ? '无' : value}
              </button>
            ))}
          </div>
          <DetailToolbarButton
            icon={Wand2}
            label="提交高清"
            busy={isSubmittingUpscale}
            disabled={!videoUrl}
            title="在画布上新建高清结果节点并提交任务"
            onClick={handleUpscaleSubmit}
          />
        </div>
      )}

      {historyOpen && isVideo && (
        <DetailHistorySection
          nodeId={node.id}
          restoreDisabled={isGenerating}
          onRestore={handleRestoreHistory}
        />
      )}

      {composeSeeds !== null && project && (
        <VideoComposeModal
          project={project}
          canvasId={canvasId}
          seedNodeIds={composeSeeds}
          // 与 VideoComposeNode.tsx 同语义（不再按 isCompose 分叉）：普通视频节点
          // 打开「剪辑」也在自己的 node.data.draftTimeline 上读写草稿——
          // VideoNodeData 本就带 [key: string]: unknown 索引签名，此前普通视频节点
          // 走的是「关闭即丢草稿」的降级路径（M4）。onPersistDraft 在弹窗卸载时
          // 无条件调用（见 VideoComposeModal 的 unmount effect），故这里始终注入。
          initialTimeline={(data.draftTimeline as ComposeTimelineState | undefined) ?? null}
          onPersistDraft={(timeline) =>
            updateNodeData(node.id, { draftTimeline: timeline } as Partial<CanvasNodeData>)
          }
          onClose={() => setComposeSeeds(null)}
          onComposed={handleComposed}
        />
      )}
    </div>
  );
}
