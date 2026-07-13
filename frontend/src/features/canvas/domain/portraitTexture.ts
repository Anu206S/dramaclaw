// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import type { FreezonePortraitTextureMode } from '@/api/ops';

/** 人像质感选择器的五个维度，每个维度三档（对齐 libtv 交互）。 */
export type PortraitTextureFusion = 'light' | 'natural' | 'deep';
export type PortraitTextureLighting = 'soft' | 'natural' | 'ambient';
export type PortraitTextureSkin = 'clear' | 'natural' | 'realistic';
export type PortraitTextureTexture = 'soft' | 'natural' | 'grain';
export type PortraitTextureSharpness = 'soft' | 'standard' | 'hd';

/** 图片生成节点上挂的人像质感调节配置（存于 node data.portraitTexture）。 */
export interface PortraitTextureSelection {
  mode: FreezonePortraitTextureMode;
  /** 人景融合：轻度对齐 / 自然融合 / 深度融合 */
  fusion: PortraitTextureFusion;
  /** 光影融合：柔和补光 / 自然匹配 / 氛围强化 */
  lighting: PortraitTextureLighting;
  /** 皮肤：清透修饰 / 自然肤质 / 真实肌理 */
  skin: PortraitTextureSkin;
  /** 纹理：柔和纹理 / 自然纹理 / 颗粒质感 */
  texture: PortraitTextureTexture;
  /** 锐度：柔焦 / 标准清晰 / 高清锐化 */
  sharpness: PortraitTextureSharpness;
  /** 目标情绪描述，仅 emotion_adjust 模式使用。 */
  emotion: string;
  /** 情绪强度，0-100，仅 emotion_adjust 模式使用。 */
  intensity: number;
}

/** 工具栏「人像质感调节」下拉项的载荷：在哪个图片节点下游建节点、预设哪种模式。 */
export interface PortraitTextureRequest {
  nodeId: string;
  mode: FreezonePortraitTextureMode;
}

/** 选择器 UI 的维度描述：i18n key 走 portraitTexture.dims.<key>.{label,options.<option>}。 */
export const PORTRAIT_TEXTURE_DIMENSIONS = [
  { key: 'fusion', options: ['light', 'natural', 'deep'] },
  { key: 'lighting', options: ['soft', 'natural', 'ambient'] },
  { key: 'skin', options: ['clear', 'natural', 'realistic'] },
  { key: 'texture', options: ['soft', 'natural', 'grain'] },
  { key: 'sharpness', options: ['soft', 'standard', 'hd'] },
] as const;

export function createDefaultPortraitTextureSelection(
  mode: FreezonePortraitTextureMode = 'portrait_adjust',
): PortraitTextureSelection {
  return {
    mode,
    fusion: 'natural',
    lighting: 'natural',
    skin: 'natural',
    texture: 'natural',
    sharpness: 'standard',
    emotion: '',
    intensity: 50,
  };
}

function pick<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : fallback;
}

export function parsePortraitTextureSelection(
  raw: unknown,
): PortraitTextureSelection | null {
  if (!raw || typeof raw !== 'object') return null;
  const value = raw as Partial<PortraitTextureSelection>;
  if (value.mode !== 'portrait_adjust' && value.mode !== 'emotion_adjust') {
    return null;
  }
  const defaults = createDefaultPortraitTextureSelection(value.mode);
  return {
    mode: value.mode,
    fusion: pick(value.fusion, ['light', 'natural', 'deep'], defaults.fusion),
    lighting: pick(value.lighting, ['soft', 'natural', 'ambient'], defaults.lighting),
    skin: pick(value.skin, ['clear', 'natural', 'realistic'], defaults.skin),
    texture: pick(value.texture, ['soft', 'natural', 'grain'], defaults.texture),
    sharpness: pick(value.sharpness, ['soft', 'standard', 'hd'], defaults.sharpness),
    emotion: typeof value.emotion === 'string' ? value.emotion : '',
    intensity:
      typeof value.intensity === 'number' && Number.isFinite(value.intensity)
        ? Math.min(100, Math.max(0, Math.round(value.intensity)))
        : defaults.intensity,
  };
}

const FUSION_PROMPTS_ZH: Record<PortraitTextureFusion, string> = {
  light: '人景融合：轻度对齐——保持人物位置不变，仅修复明显的边缘接缝。',
  natural: '人景融合：自然融合——让人物与场景在透视、比例和接触阴影上自然统一。',
  deep: '人景融合：深度融合——将人物完全融入场景，倒影、遮挡与环境色相互呼应。',
};

const LIGHTING_PROMPTS_ZH: Record<PortraitTextureLighting, string> = {
  soft: '光影融合：柔和补光——用柔和、讨喜的补光轻柔提亮人物阴影。',
  natural: '光影融合：自然匹配——人物光照的方向、强度和色温与场景保持一致。',
  ambient: '光影融合：氛围强化——强化环境氛围与电影感的光线包裹。',
};

const SKIN_PROMPTS_ZH: Record<PortraitTextureSkin, string> = {
  clear: '皮肤：清透修饰——干净通透的皮肤，去除细小瑕疵但保持真实可信。',
  natural: '皮肤：自然肤质——真实的肤色变化与柔和质感，不做塑料感磨皮。',
  realistic: '皮肤：真实肌理——可见毛孔、细小绒毛和真实的皮肤次表面散射。',
};

const TEXTURE_PROMPTS_ZH: Record<PortraitTextureTexture, string> = {
  soft: '纹理：柔和纹理——皮肤、头发与织物的微纹理平滑柔和。',
  natural: '纹理：自然纹理——忠实还原皮肤、发丝与服装的材质纹理。',
  grain: '纹理：颗粒质感——加入细微的胶片颗粒，呈现真实相机拍摄感。',
};

const SHARPNESS_PROMPTS_ZH: Record<PortraitTextureSharpness, string> = {
  soft: '锐度：柔焦——梦幻、轻微柔化的画面。',
  standard: '锐度：标准清晰——清晰锐利但不过度锐化。',
  hd: '锐度：高清锐化——高清微对比与精细的边缘细节。',
};

const FUSION_PROMPTS: Record<PortraitTextureFusion, string> = {
  light: 'Subject-scene fusion: light alignment — keep the subject placement as-is, only fix obvious edge seams.',
  natural: 'Subject-scene fusion: natural blend — harmonize the subject with the scene in perspective, scale, and contact shadows.',
  deep: 'Subject-scene fusion: deep integration — fully re-ground the subject into the scene with coherent reflections, occlusion, and ambient color spill.',
};

const LIGHTING_PROMPTS: Record<PortraitTextureLighting, string> = {
  soft: 'Lighting fusion: soft fill — gently lift shadows on the subject with soft, flattering fill light.',
  natural: 'Lighting fusion: natural match — match the subject lighting direction, intensity, and color temperature to the scene.',
  ambient: 'Lighting fusion: mood enhance — strengthen the ambient atmosphere and cinematic light wrap around the subject.',
};

const SKIN_PROMPTS: Record<PortraitTextureSkin, string> = {
  clear: 'Skin: clean retouch — clear, polished skin with minor blemishes removed while staying believable.',
  natural: 'Skin: natural finish — realistic skin tone variation and soft texture, no plastic smoothing.',
  realistic: 'Skin: true-to-life detail — visible pores, fine facial hair, and realistic subsurface scattering.',
};

const TEXTURE_PROMPTS: Record<PortraitTextureTexture, string> = {
  soft: 'Texture: soft — smooth, gentle micro-texture across skin, hair, and fabric.',
  natural: 'Texture: natural — faithful material texture on skin, hair strands, and clothing.',
  grain: 'Texture: filmic grain — add subtle photographic grain for an organic, camera-shot feel.',
};

const SHARPNESS_PROMPTS: Record<PortraitTextureSharpness, string> = {
  soft: 'Sharpness: soft focus — dreamy, slightly diffused rendering.',
  standard: 'Sharpness: standard — crisp and clear without over-sharpening.',
  hd: 'Sharpness: HD enhance — high-definition micro-contrast and refined edge detail.',
};

/**
 * 图片生成节点用的人像质感提示词块。与后端
 * `build_portrait_texture_prompt`（freezone/portrait-texture 专用接口）保持
 * 同一套约束口径，但走通用 /freezone/gen 时以精简块形式拼进用户提示词。
 * locale 传 'zh' 时输出中文提示词（跟随界面语言）。
 */
export function buildPortraitTexturePromptBlock(
  selection: PortraitTextureSelection,
  locale: 'zh' | 'en' = 'en',
): string {
  if (selection.mode === 'emotion_adjust') {
    if (locale === 'zh') {
      const emotion = selection.emotion.trim() || '自然、放松的表情';
      return (
        '人像情绪调节：\n'
        + `- 目标情绪：${emotion}；强度 ${selection.intensity}/100。\n`
        + '- 仅改变面部表情（眉、眼、视线、嘴、面颊肌肉）。\n'
        + '- 严格保持人物身份、肤质、发型、姿势、服装、背景、光线与构图不变。'
      );
    }
    const emotion = selection.emotion.trim() || 'a natural, relaxed expression';
    return (
      'PORTRAIT EMOTION ADJUST:\n'
      + `- Target emotion: ${emotion}; intensity ${selection.intensity}/100.\n`
      + '- Change only the facial expression (eyebrows, eyes, gaze, mouth, cheek muscles).\n'
      + '- Preserve facial identity, skin texture, hairstyle, pose, costume, background, '
      + 'lighting, and composition exactly.'
    );
  }
  if (locale === 'zh') {
    return (
      '人像质感调节（让人物更自然、更真实，去除 AI 塑料感）：\n'
      + `- ${FUSION_PROMPTS_ZH[selection.fusion]}\n`
      + `- ${LIGHTING_PROMPTS_ZH[selection.lighting]}\n`
      + `- ${SKIN_PROMPTS_ZH[selection.skin]}\n`
      + `- ${TEXTURE_PROMPTS_ZH[selection.texture]}\n`
      + `- ${SHARPNESS_PROMPTS_ZH[selection.sharpness]}\n`
      + '- 严格保持人物身份、表情、姿势、服装、背景与构图不变；不美颜、不改脸型；'
      + '结果必须像一张真实照片。'
    );
  }
  return (
    'PORTRAIT TEXTURE ADJUST (make the person look natural and real, remove the AI-plastic look):\n'
    + `- ${FUSION_PROMPTS[selection.fusion]}\n`
    + `- ${LIGHTING_PROMPTS[selection.lighting]}\n`
    + `- ${SKIN_PROMPTS[selection.skin]}\n`
    + `- ${TEXTURE_PROMPTS[selection.texture]}\n`
    + `- ${SHARPNESS_PROMPTS[selection.sharpness]}\n`
    + '- Preserve facial identity, expression, pose, costume, background, and composition '
    + 'exactly; no beautifying or reshaping; the result must look like a real photograph.'
  );
}
