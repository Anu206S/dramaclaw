// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab

/**
 * 情绪调节的 5×5 情绪网格（对齐 libtv 情绪选择器）。
 *
 * 坐标语义：竖轴 上=激动（高唤起）/ 下=平静（低唤起）；
 * 横轴 左=亲近 / 右=疏离。row/col 均为 0-4，(0,0) 在左上。
 *
 * 表情样例图约定放在 frontend/public/emotion-samples/<key>.png，
 * 图片就绪前 UI 会显示占位底图。
 */

export interface EmotionGridEntry {
  key: string;
  /** 网格行，0=最激动（顶部）。 */
  row: number;
  /** 网格列，0=最亲近（左侧）。 */
  col: number;
  label: string;
  labelEn: string;
  promptZh: string;
  promptEn: string;
}

export const EMOTION_GRID_SIZE = 5;

export const EMOTION_GRID: EmotionGridEntry[] = [
  // Row 0 —— 最激动
  { key: 'ecstatic', row: 0, col: 0, label: '狂喜', labelEn: 'Ecstatic', promptZh: '狂喜，眉眼舒展、笑容灿烂到极致，难以抑制的喜悦', promptEn: 'ecstatic joy, beaming uncontrollable smile, eyes crinkled with elation' },
  { key: 'excited', row: 0, col: 1, label: '兴奋', labelEn: 'Excited', promptZh: '兴奋，双眼发亮、嘴角高扬，充满能量与期待', promptEn: 'excited, sparkling wide eyes, energetic uplifted smile full of anticipation' },
  { key: 'surprised-joy', row: 0, col: 2, label: '惊喜', labelEn: 'Delighted Surprise', promptZh: '惊喜，眉毛上扬、眼睛睁大，嘴角带着不敢相信的笑意', promptEn: 'delighted surprise, raised eyebrows, wide eyes, mouth opening into a disbelieving smile' },
  { key: 'astonished', row: 0, col: 3, label: '惊愕', labelEn: 'Astonished', promptZh: '惊愕，瞳孔骤缩、嘴唇微张，被震住的瞬间', promptEn: 'astonished, startled wide eyes, parted lips, frozen in shock' },
  { key: 'furious', row: 0, col: 4, label: '暴怒', labelEn: 'Furious', promptZh: '暴怒，眉头紧锁下压、目光凌厉、咬紧牙关', promptEn: 'furious rage, fiercely knitted brows pressing down, blazing glare, clenched jaw' },
  // Row 1
  { key: 'passionate', row: 1, col: 0, label: '热情', labelEn: 'Passionate', promptZh: '热情，眼神炽热、笑容开朗，主动而有感染力', promptEn: 'warm passionate enthusiasm, bright engaging smile, radiant inviting gaze' },
  { key: 'joyful', row: 1, col: 1, label: '喜悦', labelEn: 'Joyful', promptZh: '喜悦，自然的开心笑容，眼中带光', promptEn: 'joyful, natural happy smile, light dancing in the eyes' },
  { key: 'surprised', row: 1, col: 2, label: '惊讶', labelEn: 'Surprised', promptZh: '惊讶，眉毛上挑、双眼睁大、嘴唇轻启', promptEn: 'surprised, lifted eyebrows, widened eyes, softly parted lips' },
  { key: 'anxious', row: 1, col: 3, label: '焦虑', labelEn: 'Anxious', promptZh: '焦虑，眉心微蹙、眼神游移不安、嘴唇抿紧', promptEn: 'anxious, faintly furrowed brow, unsettled darting gaze, pressed lips' },
  { key: 'angry', row: 1, col: 4, label: '愤怒', labelEn: 'Angry', promptZh: '愤怒，眉头下压、目光直逼、面部肌肉紧绷', promptEn: 'angry, lowered brows, confronting stare, tensed facial muscles' },
  // Row 2 —— 中性唤起
  { key: 'affectionate', row: 2, col: 0, label: '亲昵', labelEn: 'Affectionate', promptZh: '亲昵，目光温热柔软、嘴角含笑，毫无防备的亲近感', promptEn: 'affectionate, warm soft gaze, faint fond smile, unguarded closeness' },
  { key: 'smiling', row: 2, col: 1, label: '微笑', labelEn: 'Smiling', promptZh: '微笑，浅浅的自然笑意，松弛友善', promptEn: 'gentle natural smile, relaxed and friendly' },
  { key: 'neutral', row: 2, col: 2, label: '平和', labelEn: 'Neutral', promptZh: '平和，面部放松、目光平静自然', promptEn: 'calm neutral expression, relaxed face, steady natural gaze' },
  { key: 'vigilant', row: 2, col: 3, label: '警觉审视', labelEn: 'Alert Scrutiny', promptZh: '警觉审视，眉头轻蹙、目光锐利地打量，保持距离的戒备', promptEn: 'alert scrutiny, slightly knitted brows, sharp appraising gaze, guarded watchfulness' },
  { key: 'indifferent', row: 2, col: 4, label: '冷漠', labelEn: 'Indifferent', promptZh: '冷漠，眼神平直无温度、面部毫无起伏', promptEn: 'cold indifference, flat emotionless eyes, expressionless face' },
  // Row 3
  { key: 'tender', row: 3, col: 0, label: '温柔', labelEn: 'Tender', promptZh: '温柔，眉眼弯软、目光低垂含情、嘴角轻轻上扬', promptEn: 'tender softness, gently curved eyes, lowered loving gaze, faintly lifted mouth corners' },
  { key: 'content', row: 3, col: 1, label: '满足', labelEn: 'Content', promptZh: '满足，舒展安心的浅笑，眼神餍足', promptEn: 'contentment, eased reassured soft smile, satisfied eyes' },
  { key: 'relaxed', row: 3, col: 2, label: '放松', labelEn: 'Relaxed', promptZh: '放松，五官松弛、呼吸平缓、状态自在', promptEn: 'relaxed ease, loosened features, unhurried breathing, at-ease presence' },
  { key: 'doubtful', row: 3, col: 3, label: '疑虑', labelEn: 'Doubtful', promptZh: '疑虑，单侧眉毛微挑、目光迟疑、嘴角轻抿', promptEn: 'doubtful, one eyebrow faintly raised, hesitant gaze, lightly pursed mouth' },
  { key: 'disdainful', row: 3, col: 4, label: '轻蔑', labelEn: 'Disdainful', promptZh: '轻蔑，下颌微抬、眼神向下扫视、嘴角一侧轻撇', promptEn: 'disdain, slightly lifted chin, downward dismissive glance, one-sided curl of the lip' },
  // Row 4 —— 最平静
  { key: 'devoted', row: 4, col: 0, label: '依恋', labelEn: 'Devoted', promptZh: '依恋，安静而绵长的注视，眼底带着不舍与柔软', promptEn: 'quiet devoted attachment, long soft gaze with lingering fond reluctance' },
  { key: 'serene', row: 4, col: 1, label: '安宁', labelEn: 'Serene', promptZh: '安宁，眉目舒展、气息平和，岁月静好的松弛感', promptEn: 'serene peace, smoothed brow, tranquil breath, unhurried gentle calm' },
  { key: 'tranquil', row: 4, col: 2, label: '沉静', labelEn: 'Tranquil', promptZh: '沉静，目光深而稳、情绪内敛不外露', promptEn: 'still tranquility, deep steady gaze, composed inward emotion' },
  { key: 'melancholy', row: 4, col: 3, label: '忧郁', labelEn: 'Melancholy', promptZh: '忧郁，眼神低垂空茫、眉宇间淡淡的愁绪', promptEn: 'melancholy, lowered distant gaze, faint sorrow between the brows' },
  { key: 'detached', row: 4, col: 4, label: '疏离', labelEn: 'Detached', promptZh: '疏离，目光望向远处、神情淡漠有距离感', promptEn: 'distant detachment, gaze drifting far away, aloof remote expression' },
];

export const DEFAULT_EMOTION_KEY = 'vigilant';

export function findEmotionEntry(key: string): EmotionGridEntry | null {
  return EMOTION_GRID.find((entry) => entry.key === key) ?? null;
}

export function emotionEntryAt(row: number, col: number): EmotionGridEntry | null {
  return EMOTION_GRID.find((entry) => entry.row === row && entry.col === col) ?? null;
}

/** 表情样例图地址（public 静态资源）。图片未就绪时 onError 会走占位。 */
export function emotionSampleImageUrl(key: string): string {
  return `/emotion-samples/${key}.png`;
}
