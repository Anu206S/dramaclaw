// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useEffect, useMemo, useState } from "react";
import { Link2, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import {
  CANVAS_NODE_TYPES,
  type CanvasNode,
} from "@/features/canvas/domain/canvasNodes";
import { resolveNodeDisplayName } from "@/features/canvas/domain/nodeDisplay";
import { deriveNodeDropInfo, type DropMediaType } from "@/stores/assetDropStore";
import { useCanvasStore } from "@/stores/canvasStore";
import { readUrl } from "@/lib/url-params";
import {
  useSaveFreezoneAgentConfigItem,
  type FreezoneAgentConfigPayload,
} from "@/lib/queries/freezone-agent-config";

type AnchorNodeType = "imageGenNode" | "videoNode" | "audioNode";
type AnchorRole = "product" | "character" | "scene" | "brand" | "voice" | "general";

const ROLE_OPTIONS: Record<DropMediaType, Array<{ value: AnchorRole; label: string }>> = {
  image: [
    { value: "product", label: "商品参考" },
    { value: "character", label: "角色身份" },
    { value: "scene", label: "场景环境" },
    { value: "brand", label: "品牌视觉" },
    { value: "general", label: "通用图片" },
  ],
  video: [
    { value: "character", label: "角色动作" },
    { value: "scene", label: "镜头与场景" },
    { value: "product", label: "商品动态" },
    { value: "general", label: "通用视频" },
  ],
  audio: [
    { value: "voice", label: "音色参考" },
    { value: "brand", label: "品牌声音" },
    { value: "general", label: "通用音频" },
  ],
  model: [{ value: "general", label: "通用素材" }],
};

const ROLE_NAMES: Record<AnchorRole, string> = {
  product: "商品",
  character: "角色",
  scene: "场景",
  brand: "品牌",
  voice: "音色",
  general: "素材",
};

function anchorNodeType(mediaType: DropMediaType): AnchorNodeType | null {
  if (mediaType === "image") return "imageGenNode";
  if (mediaType === "video") return "videoNode";
  if (mediaType === "audio") return "audioNode";
  return null;
}

function safeIdPart(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/gu, "-")
    .replace(/^-+|-+$/gu, "")
    .slice(0, 48);
}

export function assetAnchorSetId(canvasId: string, nodeId: string): string {
  const canvasPart = safeIdPart(canvasId) || "canvas";
  const nodePart = safeIdPart(nodeId) || "node";
  return `anchor-${canvasPart}-${nodePart}`.slice(0, 128);
}

export function buildAssetAnchorPayload({
  canvasId,
  label,
  name,
  nodeId,
  nodeType,
  projectId,
  role,
}: {
  canvasId: string;
  label: string;
  name: string;
  nodeId: string;
  nodeType: AnchorNodeType;
  projectId: string;
  role: AnchorRole;
}): FreezoneAgentConfigPayload {
  const roleName = ROLE_NAMES[role];
  return {
    schema_version: "dramaclaw.anchor-set.v1",
    id: assetAnchorSetId(canvasId, nodeId),
    version: "1.0.0",
    enabled: true,
    name: name.trim(),
    description: `${label}作为${roleName}一致性参考；动态工作流会自动连接到兼容的生成节点。`,
    project_id: projectId,
    canvas_id: canvasId,
    anchors: [
      {
        node_id: nodeId,
        node_type: nodeType,
        label: label.trim(),
        target_item_ids: [],
      },
    ],
    tags: ["画布创建", roleName, "一致性"],
  };
}

interface AssetAnchorDialogProps {
  node: CanvasNode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AssetAnchorDialog({
  node,
  open,
  onOpenChange,
}: AssetAnchorDialogProps) {
  const dropInfo = useMemo(() => deriveNodeDropInfo(node), [node]);
  const mediaType = dropInfo?.mediaType ?? "model";
  const options = ROLE_OPTIONS[mediaType];
  const defaultRole = options[0]?.value ?? "general";
  const nodeLabel = useMemo(
    () => resolveNodeDisplayName(node.type ?? CANVAS_NODE_TYPES.imageGen, node.data),
    [node.data, node.type],
  );
  const existingAnchorSetId =
    typeof node.data.assetAnchorSetId === "string" ? node.data.assetAnchorSetId : "";
  const [role, setRole] = useState<AnchorRole>(defaultRole);
  const [name, setName] = useState(`${nodeLabel}资产锚点`);
  const saveItem = useSaveFreezoneAgentConfigItem();
  const updateNodeData = useCanvasStore((state) => state.updateNodeData);

  useEffect(() => {
    if (!open) return;
    setRole(defaultRole);
    setName(`${nodeLabel}资产锚点`);
  }, [defaultRole, nodeLabel, open]);

  const save = async () => {
    const type = anchorNodeType(mediaType);
    const { project, canvas } = readUrl();
    if (!type || !dropInfo?.sourceUrl) {
      toast.error("当前节点没有可用的图片、视频或音频素材");
      return;
    }
    if (!project || !canvas) {
      toast.error("无法识别当前项目或画布");
      return;
    }
    if (!name.trim()) {
      toast.error("请输入锚点名称");
      return;
    }

    const payload = buildAssetAnchorPayload({
      canvasId: canvas,
      label: nodeLabel,
      name,
      nodeId: node.id,
      nodeType: type,
      projectId: project,
      role,
    });
    try {
      const saved = await saveItem.mutateAsync({ kind: "anchor_sets", payload });
      updateNodeData(node.id, {
        assetAnchorSetId: String(saved.id ?? payload.id),
        assetAnchorRole: role,
      });
      toast.success(existingAnchorSetId ? "资产锚点已更新" : "已设为资产锚点");
      onOpenChange(false);
    } catch {
      toast.error("资产锚点保存失败，请重试");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Link2 className="size-4" />
            {existingAnchorSetId ? "更新资产锚点" : "设为资产锚点"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>锚点名称</Label>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>素材用途</Label>
            <Select value={role} onValueChange={(value) => setRole(value as AnchorRole)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {options.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">
            后续动态工作流可复用此素材，并自动连接到类型兼容的生成节点。
          </p>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button type="button" disabled={saveItem.isPending} onClick={() => void save()}>
            {saveItem.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
