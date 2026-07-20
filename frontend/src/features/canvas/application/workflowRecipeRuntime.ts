// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import {
  compileFreezoneRecipePrompt,
  generateFreezoneRecipeText,
  type FreezoneRecipeNodeKind,
} from '@/api/ops';

interface WorkflowCatalogRuntime {
  recipeId?: unknown;
  recipeVersion?: unknown;
  userGoal?: unknown;
  promptBuilder?: { userGoal?: unknown };
}

export interface CompileWorkflowNodePromptInput {
  nodeData: unknown;
  nodeKind: FreezoneRecipeNodeKind;
  nodePrompt: string;
  upstreamText?: string;
  fallbackPrompt: string;
  referenceMedia?: Array<{
    kind: 'image' | 'video' | 'audio';
    label?: string;
  }>;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? value as Record<string, unknown> : null;
}

function readCatalog(nodeData: unknown): WorkflowCatalogRuntime | null {
  const data = asRecord(nodeData);
  return asRecord(data?.workflowCatalog) as WorkflowCatalogRuntime | null;
}

function text(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
}

/** Compile only catalog-backed nodes; legacy/manual nodes keep their exact prompt behavior. */
export async function compileWorkflowNodePrompt(
  input: CompileWorkflowNodePromptInput,
): Promise<string> {
  const catalog = readCatalog(input.nodeData);
  const recipeId = text(catalog?.recipeId);
  if (!recipeId) return input.fallbackPrompt;

  return await compileFreezoneRecipePrompt({
    recipeId,
    recipeVersion: text(catalog?.recipeVersion),
    nodeKind: input.nodeKind,
    nodePrompt: input.nodePrompt,
    upstreamText: input.upstreamText ?? '',
    userGoal: text(catalog?.userGoal) || text(catalog?.promptBuilder?.userGoal),
    referenceMedia: input.referenceMedia,
  });
}

export async function generateWorkflowText(input: {
  nodeData: unknown;
  nodePrompt: string;
  upstreamText?: string;
}): Promise<string> {
  const catalog = readCatalog(input.nodeData);
  const recipeId = text(catalog?.recipeId);
  if (!recipeId) throw new Error('文本节点缺少 Recipe');
  return await generateFreezoneRecipeText({
    recipeId,
    recipeVersion: text(catalog?.recipeVersion),
    nodePrompt: input.nodePrompt,
    upstreamText: input.upstreamText ?? '',
    userGoal: text(catalog?.userGoal) || text(catalog?.promptBuilder?.userGoal),
  });
}
