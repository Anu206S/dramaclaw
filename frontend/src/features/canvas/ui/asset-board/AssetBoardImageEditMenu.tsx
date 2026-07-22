// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useCallback, useMemo, useState, type ReactElement, type ReactNode } from 'react';
import {
  Boxes,
  ChevronDown,
  Eraser,
  Expand,
  Globe2,
  ImageUpscale,
  Lightbulb,
  Loader2,
  Pencil,
  RotateCw,
  Wand2,
} from 'lucide-react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/shadcn/dropdown-menu';
import type {
  FreezoneOutpaintAspectRatio,
  FreezoneUpscaleScaleFactor,
} from '@/api/ops';
import { outpaintImage } from '@/features/canvas/application/imageOutpaint';
import {
  createRotateResultNode,
  discardRotateResultNode,
  rotateImageInPlace,
} from '@/features/canvas/application/imageRotate';
import { scene360Image } from '@/features/canvas/application/imageScene360';
import {
  createUpscaleResultNode,
  submitImageUpscale,
  UPSCALE_IMAGE_SIZES,
  UPSCALE_SCALE_FACTORS,
  type UpscaleImageSize,
} from '@/features/canvas/application/imageUpscale';
import { OUTPAINT_IMAGE_SIZES, type OutpaintImageSize } from '@/features/canvas/application/imageOutpaint';
import { nodeMainlineFlags } from '@/features/canvas/domain/mainlineNodeFlags';
import { type CanvasNode } from '@/features/canvas/domain/canvasNodes';
import { useFreezoneImageModels } from '@/features/canvas/hooks/useFreezoneImageModels';
import { EraseOverlay } from '@/features/canvas/ui/EraseOverlay';
import {
  DEFAULT_SHARED_MODEL_ID,
  SHARED_MODELS,
} from '@/features/canvas/ui/ProviderModelPicker';
import { RedrawOverlay } from '@/features/canvas/ui/RedrawOverlay';
import { useCanvasStore } from '@/stores/canvasStore';

import { AssetBoardMultiAngleDialog } from './AssetBoardMultiAngleDialog';
import { AssetBoardRelightDialog } from './AssetBoardRelightDialog';
import { createAssetBoardOpsRegistry } from './assetBoardOpsState';
import {
  DetailToolbarButton,
  DETAIL_TOOLBAR_BUTTON_CLASS,
} from './AssetBoardToolbarButton';

/**
 * 详情里展开的平面配置行：与视频「高清」配置行同一视觉族（细边框 + 极暗底）。
 * `w-full` 让它在外层 flex-wrap 工具条里独占一行（排在触发按钮下方）。
 */
function ConfigRow({ children }: { children: ReactNode }): ReactElement {
  return (
    <div className="flex w-full flex-wrap items-center gap-3 rounded-[6px] border border-white/10 bg-white/[0.03] px-3 py-2">
      {children}
    </div>
  );
}

function RowLabel({ children }: { children: ReactNode }): ReactElement {
  return <span className="text-[12px] text-white/40">{children}</span>;
}

/** 分段按钮组（同视频高清配置行的分辨率/降噪选择器）。 */
function SegmentedGroup<T extends string | number>({
  value,
  options,
  renderLabel,
  onChange,
}: {
  value: T;
  options: readonly T[];
  renderLabel?: (value: T) => string;
  onChange: (next: T) => void;
}): ReactElement {
  return (
    <div className="inline-flex items-center gap-0.5 rounded-[6px] border border-white/10 bg-white/[0.04] p-0.5">
      {options.map((option) => (
        <button
          key={String(option)}
          type="button"
          onClick={() => onChange(option)}
          className={`rounded-[6px] px-2 py-0.5 text-[12px] transition-colors ${
            option === value
              ? 'bg-white/15 text-white'
              : 'text-white/50 hover:bg-white/5 hover:text-white/80'
          }`}
        >
          {renderLabel ? renderLabel(option) : String(option)}
        </button>
      ))}
    </div>
  );
}

/** 开关型 chip（镜像 / 轮廓光）。 */
function ToggleChip({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}): ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-[6px] border px-2 py-0.5 text-[12px] transition-colors ${
        active
          ? 'border-white/25 bg-white/15 text-white'
          : 'border-white/10 bg-white/[0.04] text-white/50 hover:bg-white/5 hover:text-white/80'
      }`}
    >
      {label}
    </button>
  );
}

const OUTPAINT_ASPECT_LABEL: Record<FreezoneOutpaintAspectRatio, string> = {
  original: '原比例',
  '1:1': '1:1',
  '4:3': '4:3',
  '3:4': '3:4',
  '16:9': '16:9',
  '9:16': '9:16',
};
const OUTPAINT_ASPECTS: readonly FreezoneOutpaintAspectRatio[] = [
  'original',
  '1:1',
  '4:3',
  '3:4',
  '16:9',
  '9:16',
];
const OUTPAINT_NUM_IMAGES = [1, 2, 3, 4] as const;

const ROTATE_ANGLES = [90, 180, 270] as const;

/** 当前展开的配置行（互斥，同一时刻只展开一条）。多角度/重打光已改为独立弹窗，不占配置行。 */
type OpenPanel = 'hd' | 'outpaint' | 'rotate' | null;
/** 进行中的生成类操作（触发按钮转 spinner，settle 后恢复）。 */
type BusyOp = 'hd' | 'outpaint' | 'rotate' | 'pano' | null;

/**
 * 跨重挂载存活的「进行中操作 + 失败反馈」登记表。实现与设计理由已上提到
 * assetBoardOpsState.ts（视频详情工具条复用同一套），这里只建图片侧的实例。
 */
const imageOpsRegistry = createAssetBoardOpsRegistry<Exclude<BusyOp, null>>();
const { markOpStart, markOpSettled, reportOpFailure } = imageOpsRegistry;
const useInFlightOp = (nodeId: string): BusyOp => imageOpsRegistry.useInFlightOp(nodeId);
const useOpFailure = (nodeId: string): string | null =>
  imageOpsRegistry.useOpFailure(nodeId);

/**
 * 导出供测试断言（跨重挂载存活的 busy 态登记表：nodeId → 进行中的操作名）；
 * 生产代码只应通过组件内部的 markOpStart / markOpSettled 改它，不要直接操作。
 */
export const inFlightImageOps: ReadonlyMap<string, Exclude<BusyOp, null>> =
  imageOpsRegistry.inFlight;

/**
 * 仅供测试使用：清空两张模块级登记表（进行中操作 + 失败文案），避免用例间
 * 靠固定 node id（如测试用的 'img-up'）串态——生产代码永远不需要调用这个。
 */
export function __resetAssetBoardImageOpsStateForTest(): void {
  imageOpsRegistry.resetForTest();
}

interface AssetBoardImageOpsProps {
  node: CanvasNode;
  /** 已由调用方用 resolveNodeSourceImageUrl 解析的图源（无图源时调用方不渲染本组件）。 */
  imageSource: string;
}

/**
 * 故事板详情的图片编辑/生成操作区（工作流第二批：重绘/擦除/高清/扩图/旋转 +
 * 全景/多角度/重打光）。
 *
 * - 重绘 / 擦除整组件复用工作流的 RedrawOverlay / EraseOverlay（两者都 portal 到
 *   document.body 的 z-[300] 全屏层，不依赖 React Flow，详情传 node + imageSource 即可）。
 * - 高清 / 扩图 / 旋转在详情内用平面配置行选参数后直接提交，编排走
 *   application/image*（与工作流 overlay 同源，语义一致）。
 * - 多角度 / 重打光打开工作流那套完整弹窗编辑器（AssetBoardMultiAngleDialog /
 *   AssetBoardRelightDialog，同样 portal 到 document.body），球体选角/光球方向、
 *   滑杆、画质、提示词开关、算力与提交都在弹窗内容层自理。
 * - 全景无必选参数，直接确认后提交。
 *
 * 返回的是 fragment：按钮直接落在调用方的 flex-wrap 工具条里，配置行用 `w-full`
 * 自动换到下一行。
 */
export function AssetBoardImageOps({
  node,
  imageSource,
}: AssetBoardImageOpsProps): ReactElement {
  const [openPanel, setOpenPanel] = useState<OpenPanel>(null);
  // busy 态跨重挂载存活（详情工具条按 key={node.id} 整体重挂载），不是组件局部
  // state——见 inFlightImageOps 的说明。
  const busyOp = useInFlightOp(node.id);
  const opFailure = useOpFailure(node.id);
  const [redrawOpen, setRedrawOpen] = useState(false);
  const [eraseOpen, setEraseOpen] = useState(false);
  // 多角度 / 重打光：不再是内联配置行，改成打开工作流那套完整弹窗编辑器
  // （AssetBoardMultiAngleDialog / AssetBoardRelightDialog）；busy/算力/提交都在
  // 弹窗内容层自理，这里只管开关。
  const [multiAngleOpen, setMultiAngleOpen] = useState(false);
  const [relightOpen, setRelightOpen] = useState(false);

  // 高清参数（工作流 UpscaleEditorOverlay 的画质 + 放大倍数；模型走可用模型首选）。
  const [hdImageSize, setHdImageSize] = useState<UpscaleImageSize>('2K');
  const [hdScaleFactor, setHdScaleFactor] = useState<FreezoneUpscaleScaleFactor>(2);
  // 扩图参数（目标比例决定往哪个方向扩：比原图更宽→横向扩，更高→纵向扩）。
  const [outpaintAspect, setOutpaintAspect] =
    useState<FreezoneOutpaintAspectRatio>('original');
  const [outpaintSize, setOutpaintSize] = useState<OutpaintImageSize>('2K');
  const [outpaintCount, setOutpaintCount] = useState<number>(1);
  // 旋转参数（本地 canvas 变换，无后端生成）。
  const [rotateAngle, setRotateAngle] = useState<number>(90);
  const [rotateMirrorH, setRotateMirrorH] = useState(false);
  const [rotateMirrorV, setRotateMirrorV] = useState(false);

  const { models: imageModels } = useFreezoneImageModels();
  // 模型选择优先级同工作流 UpscaleEditorOverlay / OutpaintEditorOverlay：优先取
  // 默认共享模型（DEFAULT_SHARED_MODEL_ID），可用列表里没有再退到首个可用模型，
  // 都拿不到才退到硬编码 SHARED_MODELS 兜底。
  const selectedModel =
    imageModels.find((model) => model.id === DEFAULT_SHARED_MODEL_ID)
    ?? imageModels[0]
    ?? SHARED_MODELS.find((model) => model.id === DEFAULT_SHARED_MODEL_ID);
  const apiModel = selectedModel?.apiModel ?? '';
  const selectedModelId = selectedModel?.id ?? DEFAULT_SHARED_MODEL_ID;

  // 与工作流 NodeActionToolbar 同源的显隐语义：preset_managed（主线投影锁定）节点
  // 隐藏「原地改写源图」的入口——高清与旋转都是 updateNodeData 回写，会破坏
  // canonical 不可变性；其余（重绘/擦除/扩图/全景/多角度/打光）都是 spawn 出
  // user_spawned 子节点，锁定态下照常可用。
  const isPresetLocked = useMemo(() => nodeMainlineFlags(node).isPresetManaged, [node]);

  const togglePanel = useCallback((panel: Exclude<OpenPanel, null>) => {
    setOpenPanel((current) => (current === panel ? null : panel));
  }, []);

  /**
   * 生成类操作的统一收尾：结果节点已同步建好 → 立即请求视口预定位（切回工作流
   * 时视口已就位，见 Task 10），收起配置行，并把触发按钮置 busy 直到后台链 settle。
   */
  const trackSpawn = useCallback(
    (op: Exclude<BusyOp, null>, nodeId: string, completion: Promise<void>) => {
      useCanvasStore.getState().requestFocusNode(nodeId);
      setOpenPanel(null);
      markOpStart(node.id, op);
      void completion.finally(() => {
        markOpSettled(node.id);
        // 失败只写到了新建的结果节点上（generationError），源节点这边补一行
        // 红色提示——否则用户停在源节点详情面板，完全看不到刚才那次操作失败了。
        const resultNode = useCanvasStore.getState().nodes.find((n) => n.id === nodeId);
        const errorMessage = (resultNode?.data as { generationError?: unknown } | undefined)
          ?.generationError;
        if (typeof errorMessage === 'string' && errorMessage) {
          reportOpFailure(node.id, errorMessage);
        }
      });
    },
    [node.id],
  );

  const handleHdSubmit = useCallback(() => {
    if (busyOp) return;
    const resultNodeId = createUpscaleResultNode(node.id, {
      displayName: `高清放大（${hdImageSize} · ${hdScaleFactor}x）`,
      modelId: selectedModelId,
      imageSize: hdImageSize,
      scaleFactor: hdScaleFactor,
    });
    if (!resultNodeId) return;
    const completion = submitImageUpscale(resultNodeId, {
      sourceUrl: imageSource,
      scaleFactor: hdScaleFactor,
      imageSize: hdImageSize,
      model: apiModel,
    });
    if (!completion) {
      // 缺 project 起不了任务 —— 回收刚预建的占位节点，避免凭空多出一个空节点
      // （同 handleRotateSubmit 的 discardRotateResultNode 处理，upscale 侧没有
      // 对称的具名 helper，直接调 store 的 deleteNode）。
      useCanvasStore.getState().deleteNode(resultNodeId);
      return;
    }
    trackSpawn('hd', resultNodeId, completion);
  }, [
    apiModel,
    busyOp,
    hdImageSize,
    hdScaleFactor,
    imageSource,
    node.id,
    selectedModelId,
    trackSpawn,
  ]);

  const handleOutpaintSubmit = useCallback(() => {
    if (busyOp) return;
    const result = outpaintImage(node.id, imageSource, {
      displayName: '扩图',
      targetAspectRatio: outpaintAspect,
      imageSize: outpaintSize,
      numImages: outpaintCount,
      model: apiModel,
    });
    if (!result) return;
    trackSpawn('outpaint', result.nodeIds[0], result.completion);
  }, [
    apiModel,
    busyOp,
    imageSource,
    node.id,
    outpaintAspect,
    outpaintCount,
    outpaintSize,
    trackSpawn,
  ]);

  const handleRotateSubmit = useCallback(() => {
    if (busyOp) return;
    // 与工作流一致：旋转写到新建的「旋转结果」节点上，源图保持不动。
    const resultNodeId = createRotateResultNode(node.id, { displayName: '旋转结果' });
    if (!resultNodeId) return;
    const completion = rotateImageInPlace(resultNodeId, imageSource, {
      angleDeg: rotateAngle,
      mirrorH: rotateMirrorH,
      mirrorV: rotateMirrorV,
    });
    if (!completion) {
      // 缺 project 起不了任务 —— 回收刚预建的节点，避免凭空多出一个空节点。
      discardRotateResultNode(resultNodeId);
      return;
    }
    trackSpawn('rotate', resultNodeId, completion);
  }, [busyOp, imageSource, node.id, rotateAngle, rotateMirrorH, rotateMirrorV, trackSpawn]);

  const handlePanoSubmit = useCallback(() => {
    if (busyOp) return;
    if (!window.confirm('确认基于本图生成 360° 全景图？')) return;
    const result = scene360Image(node.id, imageSource, {
      displayName: '360°全景图',
      aspectRatio: '2:1',
    });
    if (!result) return;
    trackSpawn('pano', result.nodeId, result.completion);
  }, [busyOp, imageSource, node.id, trackSpawn]);

  // 编辑下拉的条目（对齐工作流 NodeActionToolbar 的编辑下拉结构）。
  const editActions = [
    { key: 'repaint', icon: Wand2, label: '重绘', run: () => setRedrawOpen(true) },
    { key: 'erase', icon: Eraser, label: '擦除', run: () => setEraseOpen(true) },
    { key: 'hd', icon: ImageUpscale, label: '高清', run: () => togglePanel('hd') },
    { key: 'outpaint', icon: Expand, label: '扩图', run: () => togglePanel('outpaint') },
    { key: 'rotate', icon: RotateCw, label: '旋转', run: () => togglePanel('rotate') },
  ]
    // 高清 / 旋转原地改写图片 → preset_managed 节点上隐藏（同工作流语义）。
    .filter((action) => !(isPresetLocked && (action.key === 'hd' || action.key === 'rotate')));

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            disabled={busyOp !== null}
            className={DETAIL_TOOLBAR_BUTTON_CLASS}
          >
            {busyOp === 'hd' || busyOp === 'outpaint' || busyOp === 'rotate' ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Pencil className="h-3.5 w-3.5" />
            )}
            编辑
            <ChevronDown className="h-3 w-3" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="start"
          sideOffset={6}
          className="z-50 min-w-[160px] border-white/10 bg-[#2e2e2e] text-white/85 shadow-xl"
        >
          {editActions.map((action) => {
            const Icon = action.icon;
            return (
              <DropdownMenuItem
                key={action.key}
                className="gap-2 rounded-[6px] text-white/80 focus:bg-white/[0.08] focus:text-white"
                onSelect={() => action.run()}
              >
                <Icon className="h-4 w-4" />
                {action.label}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>

      <DetailToolbarButton
        icon={Globe2}
        label="全景"
        busy={busyOp === 'pano'}
        disabled={busyOp !== null}
        title="基于本图生成 360° 全景图（并挂一个全景查看器节点）"
        onClick={handlePanoSubmit}
      />
      <DetailToolbarButton
        icon={Boxes}
        label="多角度"
        disabled={busyOp !== null}
        title="打开多维度编辑器（球体选角 + 画质 + 提示词）"
        onClick={() => setMultiAngleOpen(true)}
      />
      <DetailToolbarButton
        icon={Lightbulb}
        label="重打光"
        disabled={busyOp !== null}
        title="打开打光效果编辑器（方向 + 亮度/色温 + 智能模式）"
        onClick={() => setRelightOpen(true)}
      />

      {/* 操作失败兜底反馈：失败信息只写在新建结果节点上，用户还停在源节点详情
          面板看不到；这里补一行红色文案，settle 后自动消失（见 reportOpFailure
          的说明）。 */}
      {opFailure && (
        <div
          role="alert"
          className="w-full rounded-[6px] border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-[12px] text-red-300"
        >
          {opFailure}
        </div>
      )}

      {openPanel === 'hd' && (
        <ConfigRow>
          <RowLabel>画质</RowLabel>
          <SegmentedGroup
            value={hdImageSize}
            options={UPSCALE_IMAGE_SIZES}
            onChange={setHdImageSize}
          />
          <RowLabel>放大倍数</RowLabel>
          <SegmentedGroup
            value={hdScaleFactor}
            options={UPSCALE_SCALE_FACTORS}
            renderLabel={(factor) => `${factor}x`}
            onChange={setHdScaleFactor}
          />
          <DetailToolbarButton
            icon={Wand2}
            label="提交高清"
            busy={busyOp === 'hd'}
            title="在画布上新建高清结果节点并提交任务"
            onClick={handleHdSubmit}
          />
        </ConfigRow>
      )}

      {openPanel === 'outpaint' && (
        <ConfigRow>
          {/* 目标比例即扩图方向：比原图更宽 → 左右扩，更高 → 上下扩。 */}
          <RowLabel>扩图比例</RowLabel>
          <SegmentedGroup
            value={outpaintAspect}
            options={OUTPAINT_ASPECTS}
            renderLabel={(aspect) => OUTPAINT_ASPECT_LABEL[aspect]}
            onChange={setOutpaintAspect}
          />
          <RowLabel>分辨率</RowLabel>
          <SegmentedGroup
            value={outpaintSize}
            options={OUTPAINT_IMAGE_SIZES}
            onChange={setOutpaintSize}
          />
          <RowLabel>张数</RowLabel>
          <SegmentedGroup
            value={outpaintCount}
            options={OUTPAINT_NUM_IMAGES}
            renderLabel={(count) => `${count} 张`}
            onChange={setOutpaintCount}
          />
          <DetailToolbarButton
            icon={Wand2}
            label="提交扩图"
            busy={busyOp === 'outpaint'}
            title="在画布上新建扩图结果节点并提交任务"
            onClick={handleOutpaintSubmit}
          />
        </ConfigRow>
      )}

      {openPanel === 'rotate' && (
        <ConfigRow>
          <RowLabel>角度</RowLabel>
          <SegmentedGroup
            value={rotateAngle}
            options={ROTATE_ANGLES}
            renderLabel={(angle) => `${angle}°`}
            onChange={setRotateAngle}
          />
          <RowLabel>镜像</RowLabel>
          <ToggleChip
            active={rotateMirrorH}
            label="水平"
            onClick={() => setRotateMirrorH((prev) => !prev)}
          />
          <ToggleChip
            active={rotateMirrorV}
            label="垂直"
            onClick={() => setRotateMirrorV((prev) => !prev)}
          />
          <DetailToolbarButton
            icon={RotateCw}
            label="应用旋转"
            busy={busyOp === 'rotate'}
            title="在画布上新建旋转结果节点（源图保持不变）"
            onClick={handleRotateSubmit}
          />
        </ConfigRow>
      )}

      {/* 重绘 / 擦除：整组件复用工作流 overlay（自带 portal 到 body 的 z-[300] 全屏层，
          高于故事板 z-30；提交后自己在画布上建结果节点并选中）。 */}
      {redrawOpen && (
        <RedrawOverlay
          node={node}
          imageSource={imageSource}
          onClose={() => setRedrawOpen(false)}
        />
      )}
      {eraseOpen && (
        <EraseOverlay
          node={node}
          imageSource={imageSource}
          onClose={() => setEraseOpen(false)}
        />
      )}

      {/* 多角度 / 重打光：工作流那套完整弹窗编辑器（球体选角/光球方向 + 滑杆 +
          画质 + 提示词开关 + 算力 + 提交），居中弹窗 portal 到 document.body。
          提交成功后弹窗自己请求视口预定位并关闭（见 AssetBoardMultiAngleDialog /
          AssetBoardRelightDialog 的 onSubmitted 组合），这里只管开关状态。 */}
      {multiAngleOpen && (
        <AssetBoardMultiAngleDialog
          node={node}
          imageSource={imageSource}
          onClose={() => setMultiAngleOpen(false)}
        />
      )}
      {relightOpen && (
        <AssetBoardRelightDialog
          node={node}
          imageSource={imageSource}
          onClose={() => setRelightOpen(false)}
        />
      )}
    </>
  );
}
