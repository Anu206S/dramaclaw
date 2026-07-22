// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
//
// 视频生成表单与视频节点**共用**的纯常量 / 纯函数 / 纯类型。
//
// 抽这一层只为一件事：`VideoGenerationForm` 是被 `VideoNode` 引入的（单向依赖），
// 但下面这几个符号两边都要用（节点算引用上限、表单画上限角标；节点夹时长、
// 表单滑杆夹时长…）。放在表单文件里再让节点反向 import 会绕出「UI 组件导出领域
// 常量」的怪味，放这里两边都只是 import 一个无 React 依赖的小模块。

import type { VideoGenMode } from "@/features/canvas/domain/canvasNodes";
import type { FreezoneVideoAspectRatio } from "@/api/ops";

export const ASPECT_RATIOS: ReadonlyArray<FreezoneVideoAspectRatio> = [
  "auto",
  "16:9",
  "4:3",
  "1:1",
  "3:4",
  "9:16",
  "21:9",
];

// 各 genMode 对上游引用数量的硬上限。UI 用这张表把后端字段约束（多图 / 多模态
// 场景下）显式表达出来：超额 chip 标灰 + 从 @ 候选剔除，避免「prompt 引用了
// @图片10 但提交时被静默丢掉」。
//
// 表里没出现的模式默认不限制（textToVideo 不消费上游、imageToVideo 走
// `.slice(0, 9)` 自带兜底），各自走原有路径。
//   - allReference (omni)  ：image 1-9 / video 0-3 / audio 0-3。总时长 ≤ 15s
//                            的部分前端拿不到精确媒体元数据，延后交给服务端。
//   - firstLastFrame       ：仅图片 2 张（首帧 + 尾帧），不允许任何视频 / 音频。
//                            图片 >2 时另有自动切到 allReference 的兜底（见
//                            VideoNode 内部 effect）。
export const REFERENCE_CAPS_BY_MODE: Partial<
  Record<VideoGenMode, { image: number; video: number; audio: number }>
> = {
  allReference: { image: 9, video: 3, audio: 3 },
  firstLastFrame: { image: 2, video: 0, audio: 0 },
};

export function clampVideoDuration(
  value: number,
  bounds: { min: number; max: number },
): number {
  return Math.min(Math.max(Math.round(value), bounds.min), bounds.max);
}

export function isHappyHorseVideoModel(modelId: string | null | undefined): boolean {
  const normalized = String(modelId ?? "")
    .replace(/[\s._-]/g, "")
    .toLowerCase();
  return normalized.includes("happyhorse10");
}

export type ReferenceMediaItem =
  | {
      kind: "image";
      nodeId: string;
      imageUrl: string;
      displayName?: string | null;
    }
  | {
      kind: "video";
      nodeId: string;
      videoUrl: string;
      thumbUrl?: string | null;
      displayName?: string | null;
    }
  | {
      kind: "audio";
      nodeId: string;
      audioUrl: string;
      displayName?: string | null;
    };

export interface ReferenceMediaCapEntry {
  item: ReferenceMediaItem;
  /** 1-based 同类型序号（图片/视频/音频 各自累加），与 chip 角标 + @ 提及对齐。 */
  typeIndex: number;
  /** 是否在当前模式的引用上限内；表里没有的模式默认 true。 */
  withinCap: boolean;
}
