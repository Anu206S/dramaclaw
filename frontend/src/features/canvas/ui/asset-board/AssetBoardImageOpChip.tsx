// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useEffect, useRef, useState, type ReactElement } from 'react';
import {
  ArrowLeftRight,
  Compass,
  FastForward,
  Film,
  Globe,
  Grid2x2,
  Grid3x3,
  LayoutDashboard,
  Lightbulb,
  Package,
  Rewind,
  User,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react';

import {
  ASSET_BOARD_IMAGE_OPS,
  ASSET_BOARD_IMAGE_OP_CATEGORY_LABELS,
  ASSET_BOARD_IMAGE_OP_CATEGORY_ORDER,
  ASSET_BOARD_IMAGE_OP_MAP,
  clearAssetBoardImageOp,
  switchAssetBoardImageOp,
  type AssetBoardImageOpKey,
} from '@/features/canvas/application/assetBoardImageOps';
import { NODE_FLOATING_PANEL_SURFACE_CLASS } from '@/features/canvas/ui/nodeControlStyles';

/** 功能 → 图标。与工具条 `GRID_ACTION_DEFS` 同一套图标，换个视图不换认知。 */
export const ASSET_BOARD_IMAGE_OP_ICONS: Record<AssetBoardImageOpKey, LucideIcon> = {
  multiCameraGrid: Grid3x3,
  plotFourGrid: Grid2x2,
  faceThreeView: User,
  productThreeView: Package,
  serialStoryboard25: LayoutDashboard,
  cinematicLightCorrection: Film,
  characterThreeView: Users,
  frameProjection3sLater: FastForward,
  frameProjection5sEarlier: Rewind,
  scene360: Globe,
  multiAngle: Compass,
  relight: Lightbulb,
};

const OP_ITEM_BASE_CLASS =
  'flex w-full items-center gap-2 rounded-[6px] px-2 py-1.5 text-left text-xs transition-colors';
const OP_ITEM_IDLE_CLASS = 'text-white/72 hover:bg-white/[0.08] hover:text-white';
const OP_ITEM_ACTIVE_CLASS = 'bg-white/[0.14] text-white';

/**
 * 输入框顶部的**功能 chip**（对标 liblib 详情输入框里那颗「⬢ 角色设定图 ⇄」）：
 *
 * - 可点：点 chip 本体 / ⇄ 展开功能框，按四栏（分镜叙事 / 空间与机位 / 设定图 /
 *   质感调节）列出全部功能，选一个就地换掉当前功能（节点名跟着换）。
 * - 可关：× 清掉 `imageOpKey`，节点退化成普通图片生成节点，↑ 走常规文生图。
 * - chip 下方一行功能说明，告诉用户这个功能会拿当前图做什么。
 *
 * 只挂在故事板详情（宿主 `AssetBoardImageGenForm`），共用表单
 * `ImageGenerationForm` 零改动——工作流侧的节点面板不受影响。
 */
export function AssetBoardImageOpChip({
  nodeId,
  opKey,
  disabled = false,
}: {
  nodeId: string;
  opKey: AssetBoardImageOpKey;
  /** 生成中锁住换功能/关闭：在途任务还会回写这个节点，中途改 key 只会让人看错。 */
  disabled?: boolean;
}): ReactElement {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (
        triggerRef.current?.contains(event.target as Node) ||
        popoverRef.current?.contains(event.target as Node)
      ) {
        return;
      }
      setIsOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown, true);
    return () => document.removeEventListener('mousedown', onPointerDown, true);
  }, [isOpen]);

  const def = ASSET_BOARD_IMAGE_OP_MAP[opKey];
  const Icon = ASSET_BOARD_IMAGE_OP_ICONS[opKey];

  return (
    <div className="flex shrink-0 flex-col gap-1 px-3 pt-3">
      <div className="relative flex items-center gap-1.5">
        <button
          ref={triggerRef}
          type="button"
          title="切换功能"
          disabled={disabled}
          onClick={(event) => {
            event.stopPropagation();
            setIsOpen((prev) => !prev);
          }}
          className="nodrag inline-flex h-7 min-w-0 max-w-full shrink items-center gap-1.5 rounded-full border border-white/[0.16] bg-white/[0.06] pl-2 pr-1.5 text-xs font-medium text-white/88 transition-colors hover:border-white/30 hover:bg-white/[0.1] hover:text-white disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:border-white/[0.16] disabled:hover:bg-white/[0.06]"
        >
          <Icon className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">{def.label}</span>
          <ArrowLeftRight className="h-3 w-3 shrink-0 text-white/50" />
        </button>
        <button
          type="button"
          title="移除功能（改为普通图片生成）"
          disabled={disabled}
          onClick={(event) => {
            event.stopPropagation();
            setIsOpen(false);
            clearAssetBoardImageOp(nodeId);
          }}
          className="nodrag inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-white/45 transition-colors hover:bg-white/[0.1] hover:text-white disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-transparent"
        >
          <X className="h-3 w-3" strokeWidth={2.5} />
        </button>
        {isOpen && (
          <div
            ref={popoverRef}
            className={`nodrag nowheel absolute bottom-full left-0 z-50 mb-2 max-h-[320px] w-[248px] overflow-y-auto p-2 ${NODE_FLOATING_PANEL_SURFACE_CLASS}`}
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => event.stopPropagation()}
          >
            {ASSET_BOARD_IMAGE_OP_CATEGORY_ORDER.map((category) => {
              const ops = ASSET_BOARD_IMAGE_OPS.filter((op) => op.category === category);
              if (ops.length === 0) return null;
              return (
                <div key={category} className="mb-1.5 last:mb-0">
                  <div className="px-2 py-1 text-[11px] font-medium text-white/40">
                    {ASSET_BOARD_IMAGE_OP_CATEGORY_LABELS[category]}
                  </div>
                  {ops.map((op) => {
                    const OpIcon = ASSET_BOARD_IMAGE_OP_ICONS[op.key];
                    const isActive = op.key === opKey;
                    return (
                      <button
                        key={op.key}
                        type="button"
                        title={op.description}
                        onClick={() => {
                          switchAssetBoardImageOp(nodeId, op.key);
                          setIsOpen(false);
                        }}
                        className={`${OP_ITEM_BASE_CLASS} ${
                          isActive ? OP_ITEM_ACTIVE_CLASS : OP_ITEM_IDLE_CLASS
                        }`}
                      >
                        <OpIcon className="h-3.5 w-3.5 shrink-0" />
                        <span className="min-w-0 flex-1 truncate">{op.label}</span>
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
        )}
      </div>
      <p className="line-clamp-2 text-[11px] leading-4 text-white/40">{def.description}</p>
    </div>
  );
}
