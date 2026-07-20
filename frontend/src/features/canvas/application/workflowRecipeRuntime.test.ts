// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { compileFreezoneRecipePrompt, generateFreezoneRecipeText } from '@/api/ops';
import { compileWorkflowNodePrompt, generateWorkflowText } from './workflowRecipeRuntime';

vi.mock('@/api/ops', () => ({
  compileFreezoneRecipePrompt: vi.fn(),
  generateFreezoneRecipeText: vi.fn(),
}));

const compileMock = vi.mocked(compileFreezoneRecipePrompt);
const generateTextMock = vi.mocked(generateFreezoneRecipeText);

describe('workflowRecipeRuntime', () => {
  beforeEach(() => {
    compileMock.mockReset();
    generateTextMock.mockReset();
  });

  it('keeps legacy node prompts unchanged', async () => {
    const result = await compileWorkflowNodePrompt({
      nodeData: { prompt: 'manual' },
      nodeKind: 'image',
      nodePrompt: 'manual',
      fallbackPrompt: 'upstream\n\nmanual',
    });

    expect(result).toBe('upstream\n\nmanual');
    expect(compileMock).not.toHaveBeenCalled();
  });

  it('compiles catalog-backed nodes with user goal and upstream context', async () => {
    compileMock.mockResolvedValue('compiled prompt');

    const result = await compileWorkflowNodePrompt({
      nodeData: {
        workflowCatalog: {
          recipeId: 'ecommerce-scene-image',
          recipeVersion: '1',
          promptBuilder: { userGoal: '生成三张商品图' },
        },
      },
      nodeKind: 'image',
      nodePrompt: '北欧厨房',
      upstreamText: '银色咖啡机',
      fallbackPrompt: 'fallback',
      referenceMedia: [{ kind: 'image', label: '产品锚点' }],
    });

    expect(result).toBe('compiled prompt');
    expect(compileMock).toHaveBeenCalledWith({
      recipeId: 'ecommerce-scene-image',
      recipeVersion: '1',
      nodeKind: 'image',
      nodePrompt: '北欧厨房',
      upstreamText: '银色咖啡机',
      userGoal: '生成三张商品图',
      referenceMedia: [{ kind: 'image', label: '产品锚点' }],
    });
  });

  it('executes a catalog-backed text node', async () => {
    generateTextMock.mockResolvedValue('# 电商方案');

    const result = await generateWorkflowText({
      nodeData: {
        workflowCatalog: {
          recipeId: 'ecommerce-text-plan',
          recipeVersion: 1,
          userGoal: '生成三屏详情页',
        },
      },
      nodePrompt: '咖啡机卖点',
      upstreamText: '银色金属机身',
    });

    expect(result).toBe('# 电商方案');
    expect(generateTextMock).toHaveBeenCalledWith({
      recipeId: 'ecommerce-text-plan',
      recipeVersion: '1',
      nodePrompt: '咖啡机卖点',
      upstreamText: '银色金属机身',
      userGoal: '生成三屏详情页',
    });
  });
});
