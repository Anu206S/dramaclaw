// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab

const NON_SPEECH_LABELS = new Set([
  'bgm',
  'sfx',
  '持续时间',
  '负向约束',
  '环境音',
  '节奏',
  '配乐',
  '情绪',
  '时长',
  '时长匹配',
  '说明',
  '音乐',
  '音频类型',
  '音效',
  '语气',
  '语速',
]);

const BRACKETED_LABEL = /^\s*[【\[]\s*([^】\]]+?)\s*[】\]]\s*(.*)$/;
const CONTROL_LINE =
  /^\s*(?:[-*#]\s*)?(?:目标)?(?:时长|持续时间|情绪|节奏|语气|语速|音频类型|负向约束)\s*[:：]\s*.*$/i;
const BARE_DURATION = /^\s*\d+(?:\.\d+)?\s*(?:s|秒|seconds?)\s*$/i;
const TIMELINE_PREFIX =
  /^\s*(?:\[\s*)?(?:(?:\d{1,2}:)?\d{1,2}(?:\.\d+)?)\s*(?:-|–|—|~|至|→)\s*(?:(?:\d{1,2}:)?\d{1,2}(?:\.\d+)?)\s*(?:s|秒)?(?:\s*\])?\s*[:：-]?\s*/i;
const LEADING_STAGE_DIRECTIONS = /^(?:\s*[（(][^()（）\n]{1,80}[）)])+\s*/;

function normalizeLabel(value: string): string {
  return value.trim().replace(/\s+/g, '').toLowerCase();
}

function cleanSpeakableLine(value: string): string {
  return value
    .replace(TIMELINE_PREFIX, '')
    .replace(LEADING_STAGE_DIRECTIONS, '')
    .replace(/^\s*(?:[-*]\s+|#{1,6}\s*)/, '')
    .trim();
}

/**
 * Convert a mixed audio-production brief into text safe to send to TTS.
 * Duration, emotion, music and sound-effect instructions are control data and
 * must never be spoken.
 */
export function extractSpeakableAudioText(value: string): string {
  const lines = String(value || '').split(/\r?\n/);
  let section: 'speech' | 'skip' | null = null;
  const output: string[] = [];

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;

    const labelled = line.match(BRACKETED_LABEL);
    if (labelled) {
      const label = normalizeLabel(labelled[1]);
      if (NON_SPEECH_LABELS.has(label)) {
        section = 'skip';
        continue;
      }
      section = 'speech';
      const spoken = cleanSpeakableLine(labelled[2]);
      if (spoken && !CONTROL_LINE.test(spoken) && !BARE_DURATION.test(spoken)) {
        output.push(spoken);
      }
      continue;
    }

    if (section === 'skip' || CONTROL_LINE.test(line) || BARE_DURATION.test(line)) {
      continue;
    }
    const spoken = cleanSpeakableLine(line);
    if (spoken) output.push(spoken);
  }

  return output.join('\n\n');
}
