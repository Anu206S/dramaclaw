// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { describe, expect, it } from 'vitest';

import { CANVAS_NODE_TYPES, type CanvasNode } from '@/features/canvas/domain/canvasNodes';
import {
  deterministicNodeOutputIssue,
  workflowExpansionIssues,
} from './workflowQualityGate';

describe('workflowQualityGate', () => {
  it('rejects incomplete generated batches and invalid durations', () => {
    expect(deterministicNodeOutputIssue('generate_image', {
      imageUrl: '/image.png',
      count: 4,
      generationBatch: ['/1.png', '/2.png'],
    })).toContain('数量不足');
    expect(deterministicNodeOutputIssue('generate_video', {
      videoUrl: '/video.mp4',
      durationMs: 0,
    })).toContain('时长无效');
  });

  it('accepts valid output metadata', () => {
    expect(deterministicNodeOutputIssue('generate_image', {
      imageUrl: '/image.png',
      imageNaturalWidth: 2048,
      imageNaturalHeight: 2048,
    })).toBeNull();
  });

  it('detects a deleted repeated workflow node', () => {
    const nodes = [1, 3].map((instance) => ({
      id: `shot-${instance}`,
      type: CANVAS_NODE_TYPES.imageGen,
      position: { x: 0, y: 0 },
      data: {
        workflowCatalog: {
          skillId: 'video-ad',
          templateId: 'full',
          stepId: 'shots',
          stepInstance: instance,
          stepInstanceCount: 3,
        },
      },
    })) as CanvasNode[];

    expect(workflowExpansionIssues(nodes, ['shot-1'])).toEqual([
      '工作流步骤 shots 数量不完整：期望 3，当前 2。',
    ]);
  });
});
