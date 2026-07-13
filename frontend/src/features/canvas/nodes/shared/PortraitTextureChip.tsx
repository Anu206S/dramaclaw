// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useEffect, useRef, useState } from 'react';
import { SlidersHorizontal, UserRound } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { NODE_FLOATING_PANEL_SURFACE_CLASS } from '@/features/canvas/ui/nodeControlStyles';
import {
  PORTRAIT_TEXTURE_DIMENSIONS,
  type PortraitTextureSelection,
} from '@/features/canvas/domain/portraitTexture';

interface PortraitTextureChipProps {
  selection: PortraitTextureSelection;
  onChange: (next: PortraitTextureSelection) => void;
}

/**
 * 「人像质感调节」节点输入框内的常驻按钮（仅在带 portraitTexture 配置的
 * 图片生成节点上出现）。点开是人像质感选择器（对齐 libtv：人景融合 /
 * 光影融合 / 皮肤 / 纹理 / 锐度，各三档）。配置存到 node data，提交生成
 * 时拼进提示词。情绪调节后续单独做。
 */
export function PortraitTextureChip({ selection, onChange }: PortraitTextureChipProps) {
  const { t } = useTranslation();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (
        triggerRef.current?.contains(event.target as Node)
        || popoverRef.current?.contains(event.target as Node)
      ) {
        return;
      }
      setIsOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown, true);
    return () => document.removeEventListener('mousedown', onPointerDown, true);
  }, [isOpen]);

  const current = selection;

  const patch = (partial: Partial<PortraitTextureSelection>) => {
    onChange({ ...current, ...partial });
  };

  const optionPill = (active: boolean, label: string, onClick: () => void) => (
    <button
      type="button"
      className={
        active
          ? 'rounded-lg border border-white/60 bg-white/[0.16] px-3 py-1.5 text-xs font-medium text-text-dark'
          : 'rounded-lg border border-white/12 bg-transparent px-3 py-1.5 text-xs text-text-dark/78 transition-colors hover:border-white/30 hover:text-text-dark'
      }
      onClick={onClick}
    >
      {label}
    </button>
  );

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setIsOpen((prev) => !prev);
        }}
        title={t('portraitTexture.trigger')}
        className="nodrag inline-flex h-7 max-w-[200px] shrink-0 items-center gap-1.5 rounded-lg bg-white/[0.09] px-2 text-xs font-medium text-white transition-colors hover:bg-white/[0.15]"
      >
        <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-fuchsia-500 to-purple-600">
          <UserRound className="h-2.5 w-2.5 text-white" />
        </span>
        <span className="truncate">{t('portraitTexture.trigger')}</span>
        <SlidersHorizontal className="h-3 w-3 shrink-0 text-white/70" />
      </button>
      {isOpen && (
        <div
          ref={popoverRef}
          className={`nodrag nowheel absolute bottom-full left-0 z-50 mb-2 w-[320px] p-3.5 ${NODE_FLOATING_PANEL_SURFACE_CLASS}`}
          onClick={(event) => event.stopPropagation()}
        >
          <div className="flex flex-col gap-3">
            {PORTRAIT_TEXTURE_DIMENSIONS.map((dim) => (
              <div key={dim.key}>
                <div className="mb-1.5 text-xs text-text-dark/64">
                  {t(`portraitTexture.dims.${dim.key}.label`)}
                </div>
                <div className="flex items-center gap-2">
                  {dim.options.map((option) =>
                    optionPill(
                      current[dim.key] === option,
                      t(`portraitTexture.dims.${dim.key}.options.${option}`),
                      () => patch({ [dim.key]: option } as Partial<PortraitTextureSelection>),
                    ),
                  )}
                </div>
              </div>
            ))}
          </div>

          <p className="mt-3 text-[11px] leading-4 text-text-muted/80">
            {t('portraitTexture.portraitHint')}
          </p>
        </div>
      )}
    </div>
  );
}
