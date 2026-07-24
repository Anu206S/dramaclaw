// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { describe, expect, it } from 'vitest';

import { extractSpeakableAudioText } from '@/features/canvas/application/audioSpeechText';

describe('extractSpeakableAudioText', () => {
  it('keeps narration and dialogue while dropping production instructions', () => {
    expect(extractSpeakableAudioText(`
      【时长】79s
      【旁白】（低沉、缓慢）深夜的便利店，只有他一个人。
      【店员】（惊恐低语）它在看我。
      【环境音】冰柜压缩机低频运转
      【音效】心跳声渐强
      【配乐】低频不安氛围音乐
    `)).toBe('深夜的便利店，只有他一个人。\n\n它在看我。');
  });

  it('drops plain control lines and timeline prefixes', () => {
    expect(extractSpeakableAudioText(`
      时长：79s
      情绪：紧张
      0-5s：欢迎来到今天的节目。
      79s
    `)).toBe('欢迎来到今天的节目。');
  });

  it('preserves ordinary unstructured speech text', () => {
    expect(extractSpeakableAudioText('你好，欢迎回来。')).toBe('你好，欢迎回来。');
  });
});
