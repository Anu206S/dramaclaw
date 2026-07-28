// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useCallback, useEffect, useRef, useState } from 'react';

import { useCanvasStore } from '@/stores/canvasStore';

export interface OrganizeUndoSnapshot {
  /** 整理前的绝对坐标,只含这次整理真正会碰到的节点。 */
  positions: Record<string, { x: number; y: number }>;
  /** 整理前的视口 —— 整理会顺手 fitView,不存下来「还原」就只能还原一半。 */
  viewport: { x: number; y: number; zoom: number };
  /** 拍快照时 store 的编辑计数,用来判断快照有没有过期。 */
  editSeq: number;
}

/**
 * 「整理画布」的后悔药。整理一下挪走几十个节点、顺带换掉视口,而入口就是缩放条里
 * 那个 20px 的按钮 —— 误点之后光靠 ⌘Z 只能退回坐标,视口回不来。
 *
 * 快照的有效期只有「整理完还没动过别的」这一小段:用户一旦又拖了节点、加了节点,
 * 再按还原就会连他后来的改动一起抹掉。所以这里盯着 store 的编辑计数,一有新编辑
 * 就静默丢掉快照(等同于用户选了「保留」),宁可少给一次后悔机会,也不能吃掉工作量。
 */
export function useOrganizeUndo() {
  const [pending, setPending] = useState<OrganizeUndoSnapshot | null>(null);
  // consume() 要在同一个事件里读到最新值,不能等 setState 生效,因此额外挂一份 ref。
  const pendingRef = useRef<OrganizeUndoSnapshot | null>(null);

  const write = useCallback((next: OrganizeUndoSnapshot | null) => {
    pendingRef.current = next;
    setPending(next);
  }, []);

  /**
   * 记下一次整理。**必须在写入新坐标之后调用** —— 编辑计数的基准要把整理自己那
   * 一次算进去,否则确认条会被自己的编辑立刻收掉。
   */
  const capture = useCallback(
    (
      positions: OrganizeUndoSnapshot['positions'],
      viewport: OrganizeUndoSnapshot['viewport'],
    ) => {
      write({
        positions,
        viewport,
        editSeq: useCanvasStore.getState().userEditsSinceHydrate,
      });
    },
    [write],
  );

  /** 用户选「保留」:丢掉快照,收起确认条。 */
  const keep = useCallback(() => {
    write(null);
  }, [write]);

  /** 用户选「还原」:取出快照并收起确认条,由调用方负责把坐标和视口写回去。 */
  const consume = useCallback((): OrganizeUndoSnapshot | null => {
    const snapshot = pendingRef.current;
    write(null);
    return snapshot;
  }, [write]);

  useEffect(() => {
    if (!pending) {
      return;
    }
    return useCanvasStore.subscribe((state) => {
      if (state.userEditsSinceHydrate !== pending.editSeq) {
        write(null);
      }
    });
  }, [pending, write]);

  return { pending, capture, keep, consume };
}
