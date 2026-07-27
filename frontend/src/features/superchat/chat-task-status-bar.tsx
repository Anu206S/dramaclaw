// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ListTodo,
  LoaderCircle,
  LocateFixed,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { resolveNodeDisplayName } from "@/features/canvas/domain/nodeDisplay";
import type { CanvasNode } from "@/features/canvas/domain/canvasNodes";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/app-store";
import { useCanvasStore } from "@/stores/canvasStore";
import { displayLabel, isActive, isTerminal } from "@/task-center/derivations";
import { useTaskCenterStore } from "@/task-center/store";
import type { TaskState } from "@/task-center/types";

const RECENT_TERMINAL_MS = 60_000;

export interface ChatTaskItem {
  task: TaskState;
  nodeId: string | null;
  nodeLabel: string | null;
}

function nonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function terminalTimestamp(task: TaskState): number {
  const parsed = Date.parse(task.completed_at || task.updated_at);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function selectChatTaskItems(
  tasks: Iterable<TaskState>,
  nodes: readonly CanvasNode[],
  canvasId: string | null,
  now = Date.now(),
): ChatTaskItem[] {
  if (!canvasId) return [];

  const nodeIds = new Set(nodes.map((node) => node.id));
  const nodesByTaskKey = new Map<string, CanvasNode>();
  for (const node of nodes) {
    const key = nonEmptyString(
      (node.data as { generationTaskKey?: unknown }).generationTaskKey,
    );
    if (key) nodesByTaskKey.set(key, node);
  }

  const items: ChatTaskItem[] = [];
  for (const task of tasks) {
    const metadata = task.metadata ?? {};
    const mappedNode = nodesByTaskKey.get(task.task_key) ?? null;
    const metadataCanvasId = nonEmptyString(metadata.canvas_id);
    const metadataNodeId =
      nonEmptyString(metadata.skill_node_id) ?? nonEmptyString(metadata.node_id);
    const belongsToCanvas =
      Boolean(mappedNode) ||
      metadataCanvasId === canvasId ||
      Boolean(metadataNodeId && nodeIds.has(metadataNodeId));
    if (!belongsToCanvas) continue;

    const visible =
      isActive(task) ||
      (isTerminal(task) && now - terminalTimestamp(task) <= RECENT_TERMINAL_MS);
    if (!visible) continue;

    const node = mappedNode ?? nodes.find((candidate) => candidate.id === metadataNodeId) ?? null;
    items.push({
      task,
      nodeId: node?.id ?? null,
      nodeLabel:
        node && node.type
          ? resolveNodeDisplayName(node.type, node.data)
          : null,
    });
  }

  return items.sort((left, right) => {
    const activeDelta = Number(isActive(right.task)) - Number(isActive(left.task));
    if (activeDelta) return activeDelta;
    return Date.parse(right.task.updated_at) - Date.parse(left.task.updated_at);
  });
}

function taskProgress(task: TaskState): number {
  if (task.status === "completed") return 100;
  return Math.max(0, Math.min(100, Math.round((task.progress || 0) * 100)));
}

export function ChatTaskStatusBar({ canvasId }: { canvasId: string | null }) {
  const { t } = useTranslation();
  const tasks = useTaskCenterStore((state) => state.tasks);
  const nodes = useCanvasStore((state) => state.nodes);
  const setTaskPanelOpen = useAppStore((state) => state.setTaskPanelOpen);
  const setSelectedTask = useTaskCenterStore((state) => state.setSelected);
  const [expanded, setExpanded] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const items = useMemo(
    () => selectChatTaskItems(tasks.values(), nodes, canvasId, now),
    [tasks, nodes, canvasId, now],
  );
  const hasTerminalItems = items.some(({ task }) => isTerminal(task));

  useEffect(() => {
    if (!hasTerminalItems) return;
    const timer = window.setInterval(() => setNow(Date.now()), 5_000);
    return () => window.clearInterval(timer);
  }, [hasTerminalItems]);

  useEffect(() => {
    if (items.length === 0) setExpanded(false);
  }, [items.length]);

  if (items.length === 0) return null;

  const activeItems = items.filter(({ task }) => isActive(task));
  const runningCount = activeItems.filter(({ task }) => task.status === "running").length;
  const waitingCount = activeItems.length - runningCount;
  const failedCount = items.filter(({ task }) => task.status === "failed").length;
  const completedCount = items.filter(({ task }) => task.status === "completed").length;
  const leading = activeItems[0] ?? items[0];
  const summary = activeItems.length
    ? [
        runningCount
          ? t("taskCenter.chatStatus.running", { count: runningCount })
          : null,
        waitingCount
          ? t("taskCenter.chatStatus.waiting", { count: waitingCount })
          : null,
      ].filter(Boolean).join(" · ")
    : failedCount
      ? t("taskCenter.chatStatus.failed", { count: failedCount })
      : t("taskCenter.chatStatus.completed", { count: completedCount });

  const openTask = (taskKey: string) => {
    setSelectedTask(taskKey);
    setTaskPanelOpen(true);
  };

  const locateNode = (nodeId: string) => {
    const store = useCanvasStore.getState();
    if (!store.nodes.some((node) => node.id === nodeId)) return;
    store.onNodesChange(
      store.nodes.map((node) => ({
        id: node.id,
        type: "select" as const,
        selected: node.id === nodeId,
      })),
    );
    store.setSelectedNode(nodeId);
    store.requestFocusNode(nodeId);
  };

  return (
    <section className="mx-auto mb-2 w-full overflow-hidden rounded-lg border border-white/10 bg-background/92 shadow-sm backdrop-blur-xl">
      <div className="flex h-10 min-w-0 items-center gap-2 px-2.5">
        {activeItems.length ? (
          <LoaderCircle className="size-4 shrink-0 animate-spin text-primary" />
        ) : failedCount ? (
          <AlertCircle className="size-4 shrink-0 text-destructive" />
        ) : (
          <CheckCircle2 className="size-4 shrink-0 text-success" />
        )}
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          <span className="shrink-0 text-xs font-medium text-foreground" aria-live="polite">
            {summary}
          </span>
          <span className="truncate text-xs text-muted-foreground">
            {leading.nodeLabel ?? displayLabel(leading.task, t)}
          </span>
          <ChevronDown
            className={cn(
              "ml-auto size-4 shrink-0 text-muted-foreground transition-transform",
              expanded && "rotate-180",
            )}
          />
        </button>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="size-7 shrink-0"
          title={t("taskCenter.panel.open")}
          aria-label={t("taskCenter.panel.open")}
          onClick={() => openTask(leading.task.task_key)}
        >
          <ListTodo className="size-4" />
        </Button>
      </div>

      {expanded ? (
        <div className="max-h-52 overflow-y-auto border-t border-white/8 px-2 py-1.5">
          {items.map(({ task, nodeId, nodeLabel }) => {
            const progress = taskProgress(task);
            return (
              <div
                key={task.task_key}
                className="flex min-h-11 items-center gap-2 border-b border-white/6 px-1.5 py-1.5 last:border-b-0"
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() => openTask(task.task_key)}
                >
                  <span className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate text-foreground">
                      {nodeLabel ?? displayLabel(task, t)}
                    </span>
                    <span className="shrink-0 tabular-nums text-muted-foreground">
                      {t(`taskCenter.status.${task.status}`)}
                      {isActive(task) ? ` · ${progress}%` : ""}
                    </span>
                  </span>
                  <span className="mt-1 block h-1 overflow-hidden rounded-full bg-white/8">
                    <span
                      className={cn(
                        "block h-full rounded-full transition-[width] duration-300",
                        task.status === "failed"
                          ? "bg-destructive"
                          : task.status === "completed"
                            ? "bg-success"
                            : "bg-primary",
                      )}
                      style={{ width: `${progress}%` }}
                    />
                  </span>
                </button>
                {nodeId ? (
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="size-7 shrink-0"
                    title={t("taskCenter.chatStatus.locateNode")}
                    aria-label={t("taskCenter.chatStatus.locateNode")}
                    onClick={() => locateNode(nodeId)}
                  >
                    <LocateFixed className="size-3.5" />
                  </Button>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
