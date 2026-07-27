// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useMemo, useState, type ReactNode } from "react";
import { Pencil, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { validateFreezoneAgentConfigPayload } from "@/lib/freezone-agent-config-schema";
import {
  useDeleteFreezoneAgentConfigItem,
  useFreezoneAgentConfigItems,
  useSaveFreezoneAgentConfigItem,
  type FreezoneAgentConfigPayload,
} from "@/lib/queries/freezone-agent-config";

type CreativeLibraryKind = "aesthetics" | "anchor_sets";
type AnchorNodeType = "imageGenNode" | "videoNode" | "audioNode";

interface CreativeLibraryProps {
  kind: CreativeLibraryKind;
}

interface AestheticDraft {
  enabled: boolean;
  id: string;
  name: string;
  description: string;
  promptGuide: string;
  negativePrompt: string;
  tags: string;
  outputKinds: string[];
}

interface AnchorDraft {
  key: number;
  nodeId: string;
  nodeType: AnchorNodeType;
  label: string;
  targetItemIds: string;
}

interface AnchorSetDraft {
  enabled: boolean;
  id: string;
  name: string;
  description: string;
  projectId: string;
  canvasId: string;
  tags: string;
  anchors: AnchorDraft[];
}

const OUTPUT_KINDS = ["text", "image", "video", "audio"] as const;
const ANCHOR_NODE_TYPES: AnchorNodeType[] = [
  "imageGenNode",
  "videoNode",
  "audioNode",
];

function stringValue(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map(stringValue).map((item) => item.trim()).filter(Boolean)
    : [];
}

function splitList(value: string): string[] {
  return value.split(/[\n,，]/u).map((item) => item.trim()).filter(Boolean);
}

function emptyAesthetic(): AestheticDraft {
  return {
    enabled: true,
    id: "",
    name: "",
    description: "",
    promptGuide: "",
    negativePrompt: "",
    tags: "",
    outputKinds: ["image", "video"],
  };
}

function aestheticFromPayload(payload: FreezoneAgentConfigPayload): AestheticDraft {
  return {
    enabled: payload.enabled !== false,
    id: stringValue(payload.id),
    name: stringValue(payload.name),
    description: stringValue(payload.description),
    promptGuide: stringValue(payload.prompt_guide),
    negativePrompt: stringValue(payload.negative_prompt),
    tags: stringList(payload.tags).join(", "),
    outputKinds: stringList(payload.output_kinds),
  };
}

function newAnchor(key = Date.now()): AnchorDraft {
  return {
    key,
    nodeId: "",
    nodeType: "imageGenNode",
    label: "",
    targetItemIds: "",
  };
}

function anchorSetFromPayload(payload: FreezoneAgentConfigPayload): AnchorSetDraft {
  const anchors = Array.isArray(payload.anchors) ? payload.anchors : [];
  return {
    enabled: payload.enabled !== false,
    id: stringValue(payload.id),
    name: stringValue(payload.name),
    description: stringValue(payload.description),
    projectId: stringValue(payload.project_id),
    canvasId: stringValue(payload.canvas_id),
    tags: stringList(payload.tags).join(", "),
    anchors: anchors.map((value, index) => {
      const anchor = value && typeof value === "object"
        ? value as Record<string, unknown>
        : {};
      const nodeType = stringValue(anchor.node_type);
      return {
        key: Date.now() + index,
        nodeId: stringValue(anchor.node_id),
        nodeType: ANCHOR_NODE_TYPES.includes(nodeType as AnchorNodeType)
          ? nodeType as AnchorNodeType
          : "imageGenNode",
        label: stringValue(anchor.label),
        targetItemIds: stringList(anchor.target_item_ids).join(", "),
      };
    }),
  };
}

export function FreezoneCreativeLibrarySettings({ kind }: CreativeLibraryProps) {
  const isAesthetic = kind === "aesthetics";
  const query = useFreezoneAgentConfigItems(kind);
  const saveItem = useSaveFreezoneAgentConfigItem();
  const deleteItem = useDeleteFreezoneAgentConfigItem();
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<FreezoneAgentConfigPayload | null | undefined>();

  const items = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (query.data ?? []).filter((item) => {
      if (!needle) return true;
      return [
        stringValue(item.id),
        stringValue(item.name),
        stringValue(item.description),
        ...stringList(item.tags),
      ].join(" ").toLowerCase().includes(needle);
    });
  }, [query.data, search]);

  const toggleEnabled = async (item: FreezoneAgentConfigPayload, enabled: boolean) => {
    try {
      await saveItem.mutateAsync({
        kind,
        payload: { ...stripMetadata(item), enabled },
      });
    } catch {
      toast.error("保存失败，请检查配置内容");
    }
  };

  const removeItem = async (item: FreezoneAgentConfigPayload) => {
    const id = stringValue(item.id);
    if (!id) return;
    try {
      await deleteItem.mutateAsync({ kind, id });
      toast.success("配置已删除");
    } catch {
      toast.error("删除失败，请重试");
    }
  };

  return (
    <section className="px-5 py-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-heading text-sm font-medium text-foreground">
            {isAesthetic ? "审美风格" : "资产锚点"}
          </h3>
          <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
            {isAesthetic
              ? "管理可跨 Skill 复用的视觉风格，工作流确认后会参与节点提示词编译。"
              : "保存画布中的角色、商品、场景等节点引用，并绑定到动态工作流步骤。"}
          </p>
        </div>
        <Button type="button" size="sm" onClick={() => setEditing(null)}>
          <Plus className="size-3.5" />
          新增
        </Button>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={isAesthetic ? "搜索审美风格" : "搜索资产锚点"}
            className="h-9 pl-9"
          />
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          title="刷新"
          onClick={() => void query.refetch()}
        >
          <RefreshCw className="size-3.5" />
        </Button>
        <span className="text-[11px] text-muted-foreground">共 {items.length} 项</span>
      </div>

      <div className="mt-4 space-y-2">
        {query.isLoading ? (
          <p className="py-10 text-center text-xs text-muted-foreground">加载中...</p>
        ) : query.isError ? (
          <p className="py-10 text-center text-xs text-destructive">加载失败，请刷新重试。</p>
        ) : items.length === 0 ? (
          <p className="py-10 text-center text-xs text-muted-foreground">
            {isAesthetic ? "暂无审美风格" : "暂无资产锚点"}
          </p>
        ) : items.map((item) => {
          const id = stringValue(item.id);
          const builtin = item._catalog_source === "builtin";
          const anchorCount = Array.isArray(item.anchors) ? item.anchors.length : 0;
          return (
            <article
              key={id}
              className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-md border border-white/[0.08] bg-white/[0.025] px-3 py-2.5"
            >
              <Checkbox
                checked={item.enabled !== false}
                aria-label={`切换 ${stringValue(item.name) || id} 启用状态`}
                onCheckedChange={(checked) => void toggleEnabled(item, checked === true)}
              />
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm text-foreground">
                    {stringValue(item.name) || id}
                  </span>
                  {builtin ? (
                    <span className="rounded border border-white/[0.1] px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      内置
                    </span>
                  ) : null}
                  {!isAesthetic ? (
                    <span className="text-[10px] text-muted-foreground">
                      {anchorCount} 个锚点
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 truncate text-[11px] text-muted-foreground">
                  {stringValue(item.description) || id}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  title="编辑"
                  onClick={() => setEditing(item)}
                >
                  <Pencil className="size-3.5" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  title="删除"
                  onClick={() => void removeItem(item)}
                >
                  <Trash2 className="size-3.5 text-destructive" />
                </Button>
              </div>
            </article>
          );
        })}
      </div>

      {isAesthetic ? (
        <AestheticEditor
          key={`aesthetic-${stringValue(editing?.id) || "new"}`}
          open={editing !== undefined}
          initial={editing ? aestheticFromPayload(editing) : emptyAesthetic()}
          onClose={() => setEditing(undefined)}
          onSave={async (payload) => {
            await saveItem.mutateAsync({ kind, payload });
            setEditing(undefined);
            toast.success("审美风格已保存");
          }}
          saving={saveItem.isPending}
        />
      ) : (
        <AnchorSetEditor
          key={`anchor-${stringValue(editing?.id) || "new"}`}
          open={editing !== undefined}
          initial={editing ? anchorSetFromPayload(editing) : {
            enabled: true,
            id: "",
            name: "",
            description: "",
            projectId: "",
            canvasId: "",
            tags: "",
            anchors: [newAnchor()],
          }}
          onClose={() => setEditing(undefined)}
          onSave={async (payload) => {
            await saveItem.mutateAsync({ kind, payload });
            setEditing(undefined);
            toast.success("资产锚点已保存");
          }}
          saving={saveItem.isPending}
        />
      )}
    </section>
  );
}

function AestheticEditor({
  open,
  initial,
  onClose,
  onSave,
  saving,
}: {
  open: boolean;
  initial: AestheticDraft;
  onClose: () => void;
  onSave: (payload: FreezoneAgentConfigPayload) => Promise<void>;
  saving: boolean;
}) {
  const [draft, setDraft] = useState(initial);
  const save = async () => {
    const payload = {
      schema_version: "dramaclaw.aesthetic.v1",
      id: draft.id.trim(),
      version: "1.0.0",
      enabled: draft.enabled,
      name: draft.name.trim(),
      description: draft.description.trim(),
      prompt_guide: draft.promptGuide.trim(),
      negative_prompt: draft.negativePrompt.trim(),
      tags: splitList(draft.tags),
      output_kinds: draft.outputKinds,
    };
    const validation = validateFreezoneAgentConfigPayload("aesthetics", payload);
    if (!validation.ok) {
      toast.error(validation.message);
      return;
    }
    try {
      await onSave(payload);
    } catch {
      toast.error("保存失败，请检查配置内容");
    }
  };
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent className="max-h-[82vh] overflow-y-auto sm:max-w-[680px]">
        <DialogHeader><DialogTitle>{initial.id ? "编辑审美风格" : "新增审美风格"}</DialogTitle></DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="ID"><Input value={draft.id} disabled={Boolean(initial.id)} onChange={(event) => setDraft({ ...draft, id: event.target.value })} placeholder="cinematic-neon" /></Field>
          <Field label="名称"><Input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="霓虹电影感" /></Field>
          <div className="sm:col-span-2"><Field label="说明"><Input value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></Field></div>
          <div className="sm:col-span-2"><Field label="视觉指引"><Textarea rows={5} value={draft.promptGuide} onChange={(event) => setDraft({ ...draft, promptGuide: event.target.value })} /></Field></div>
          <div className="sm:col-span-2"><Field label="负面约束"><Textarea rows={3} value={draft.negativePrompt} onChange={(event) => setDraft({ ...draft, negativePrompt: event.target.value })} /></Field></div>
          <Field label="标签"><Input value={draft.tags} onChange={(event) => setDraft({ ...draft, tags: event.target.value })} placeholder="电影感, 霓虹, 都市" /></Field>
          <Field label="适用输出">
            <div className="flex h-9 items-center gap-3">
              {OUTPUT_KINDS.map((kind) => (
                <label key={kind} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Checkbox checked={draft.outputKinds.includes(kind)} onCheckedChange={(checked) => setDraft({
                    ...draft,
                    outputKinds: checked === true
                      ? [...new Set([...draft.outputKinds, kind])]
                      : draft.outputKinds.filter((item) => item !== kind),
                  })} />
                  {kind}
                </label>
              ))}
            </div>
          </Field>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>取消</Button>
          <Button type="button" disabled={saving} onClick={() => void save()}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AnchorSetEditor({
  open,
  initial,
  onClose,
  onSave,
  saving,
}: {
  open: boolean;
  initial: AnchorSetDraft;
  onClose: () => void;
  onSave: (payload: FreezoneAgentConfigPayload) => Promise<void>;
  saving: boolean;
}) {
  const [draft, setDraft] = useState(initial);
  const patchAnchor = (key: number, changes: Partial<AnchorDraft>) => {
    setDraft({
      ...draft,
      anchors: draft.anchors.map((anchor) => anchor.key === key
        ? { ...anchor, ...changes }
        : anchor),
    });
  };
  const save = async () => {
    const payload = {
      schema_version: "dramaclaw.anchor-set.v1",
      id: draft.id.trim(),
      version: "1.0.0",
      enabled: draft.enabled,
      name: draft.name.trim(),
      description: draft.description.trim(),
      project_id: draft.projectId.trim(),
      canvas_id: draft.canvasId.trim(),
      tags: splitList(draft.tags),
      anchors: draft.anchors.map((anchor) => ({
        node_id: anchor.nodeId.trim(),
        node_type: anchor.nodeType,
        label: anchor.label.trim(),
        target_item_ids: splitList(anchor.targetItemIds),
      })),
    };
    const validation = validateFreezoneAgentConfigPayload("anchor_sets", payload);
    if (!validation.ok) {
      toast.error(validation.message);
      return;
    }
    try {
      await onSave(payload);
    } catch {
      toast.error("保存失败，请检查配置内容");
    }
  };
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent className="max-h-[82vh] overflow-y-auto sm:max-w-[820px]">
        <DialogHeader><DialogTitle>{initial.id ? "编辑资产锚点" : "新增资产锚点"}</DialogTitle></DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="ID"><Input value={draft.id} disabled={Boolean(initial.id)} onChange={(event) => setDraft({ ...draft, id: event.target.value })} placeholder="brand-product-assets" /></Field>
          <Field label="名称"><Input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="品牌商品资产" /></Field>
          <div className="sm:col-span-2"><Field label="说明"><Input value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></Field></div>
          <Field label="项目 ID"><Input value={draft.projectId} onChange={(event) => setDraft({ ...draft, projectId: event.target.value })} /></Field>
          <Field label="画布 ID"><Input value={draft.canvasId} onChange={(event) => setDraft({ ...draft, canvasId: event.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="标签"><Input value={draft.tags} onChange={(event) => setDraft({ ...draft, tags: event.target.value })} /></Field></div>
        </div>
        <div className="mt-1 flex items-center justify-between">
          <Label>锚点节点</Label>
          <Button type="button" variant="outline" size="sm" onClick={() => setDraft({ ...draft, anchors: [...draft.anchors, newAnchor()] })}>
            <Plus className="size-3.5" />添加锚点
          </Button>
        </div>
        <div className="space-y-2">
          {draft.anchors.map((anchor) => (
            <div key={anchor.key} className="grid gap-2 rounded-md border border-white/[0.08] p-3 sm:grid-cols-[1fr_150px_1fr_auto]">
              <Input value={anchor.nodeId} onChange={(event) => patchAnchor(anchor.key, { nodeId: event.target.value })} placeholder="画布节点 ID" />
              <Select value={anchor.nodeType} onValueChange={(value) => patchAnchor(anchor.key, { nodeType: value as AnchorNodeType })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{ANCHOR_NODE_TYPES.map((type) => <SelectItem key={type} value={type}>{type}</SelectItem>)}</SelectContent>
              </Select>
              <Input value={anchor.label} onChange={(event) => patchAnchor(anchor.key, { label: event.target.value })} placeholder="显示名称" />
              <Button type="button" variant="ghost" size="icon-sm" title="删除锚点" disabled={draft.anchors.length === 1} onClick={() => setDraft({ ...draft, anchors: draft.anchors.filter((item) => item.key !== anchor.key) })}>
                <Trash2 className="size-3.5 text-destructive" />
              </Button>
              <div className="sm:col-span-4">
                <Input value={anchor.targetItemIds} onChange={(event) => patchAnchor(anchor.key, { targetItemIds: event.target.value })} placeholder="绑定目标步骤 ID，逗号分隔；留空表示应用到所有媒体节点" />
              </div>
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>取消</Button>
          <Button type="button" disabled={saving} onClick={() => void save()}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <div className="space-y-1.5"><Label>{label}</Label>{children}</div>;
}

function stripMetadata(payload: FreezoneAgentConfigPayload): FreezoneAgentConfigPayload {
  return Object.fromEntries(
    Object.entries(payload).filter(([key]) => !key.startsWith("_catalog_")),
  );
}
