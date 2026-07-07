// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import {
  useMemo,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ChevronDown, Download, Pencil, Plus, Search, Trash2, Upload, X } from "lucide-react";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useDeleteFreezoneAgentConfigItem,
  useFreezoneAgentConfigItems,
  useSaveFreezoneAgentConfigItem,
  type FreezoneAgentConfigPayload,
} from "@/lib/queries/freezone-agent-config";
import { cn } from "@/lib/utils";

type FreezoneCatalogKind = "skills" | "recipes";
type RecipeGenerationType = "image" | "video" | "audio" | "text";

interface SkillDraft {
  id: string;
  category: string;
  description: string;
  keywords: string[];
  nodeScopes: string[];
  planningNotes: string;
  promptGuide: string;
  conductRules: string;
  qualityThreshold: string;
  domainConstraints: string;
}

interface RecipeDraft {
  id: string;
  name: string;
  outputKind: RecipeGenerationType;
  actionKeys: string[];
  systemPrompt: string;
  mustHaveItems: string[];
  planningPrompt: string;
  resultSummary: string;
  sourceMediaRequired: boolean;
  forceEnhancement: boolean;
}

interface RatingBandDraft {
  id: number;
  score: string;
  description: string;
}

interface DimensionDraft {
  id: number;
  name: string;
  weight: string;
  description: string;
}

interface FreezoneSkillRecipeSettingsProps {
  kind: FreezoneCatalogKind;
  open: boolean;
}

export function FreezoneSkillRecipeSettings({
  kind,
}: FreezoneSkillRecipeSettingsProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [addingSkill, setAddingSkill] = useState(false);
  const [addingRecipe, setAddingRecipe] = useState(false);
  const [editingSkill, setEditingSkill] = useState<FreezoneAgentConfigPayload | null>(null);
  const [editingRecipe, setEditingRecipe] = useState<FreezoneAgentConfigPayload | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const catalogQuery = useFreezoneAgentConfigItems(kind);
  const saveCatalogItem = useSaveFreezoneAgentConfigItem();
  const deleteCatalogItem = useDeleteFreezoneAgentConfigItem();
  const isSkills = kind === "skills";
  const catalogItems = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const items = (catalogQuery.data ?? []).map((item) => toManagedCatalogItem(item, kind));
    if (!needle) return items;
    return items.filter((item) =>
      [item.id, item.title, item.description, ...item.tags].join(" ").toLowerCase().includes(needle),
    );
  }, [catalogQuery.data, query, kind]);
  const itemCount = catalogItems.length;
  const selectedItems = catalogItems.filter((item) => selectedIds.has(item.id));
  const selectedCount = selectedItems.length;
  const allVisibleSelected = itemCount > 0 && selectedCount === itemCount;

  useEffect(() => {
    setSelectedIds(new Set());
  }, [kind]);

  const saveItem = async (payload: FreezoneAgentConfigPayload) => {
    const cleanPayload = stripCatalogMetadata(payload);
    if (!validateCatalogPayload(kind, cleanPayload)) {
      toast.error(t("settings.freezoneCatalog.saveFailed"));
      return;
    }
    try {
      await saveCatalogItem.mutateAsync({ kind, payload: cleanPayload });
      toast.success(t("settings.freezoneCatalog.saved"));
      if (kind === "skills") {
        setAddingSkill(false);
        setEditingSkill(null);
      } else {
        setAddingRecipe(false);
        setEditingRecipe(null);
      }
    } catch {
      toast.error(t("settings.freezoneCatalog.saveFailed"));
    }
  };

  const toggleItemEnabled = async (item: ManagedCatalogItem, enabled: boolean) => {
    try {
      const payload =
        item.builtin && !item.customized
          ? { id: item.id, enabled }
          : { ...stripCatalogMetadata(item.payload), enabled };
      await saveCatalogItem.mutateAsync({
        kind,
        payload,
      });
    } catch {
      toast.error(t("settings.freezoneCatalog.saveFailed"));
    }
  };

  const deleteItem = async (item: ManagedCatalogItem) => {
    try {
      await deleteCatalogItem.mutateAsync({ kind, id: item.id });
      setSelectedIds((current) => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
      toast.success(t("settings.freezoneCatalog.deleted"));
    } catch {
      toast.error(t("settings.freezoneCatalog.deleteFailed"));
    }
  };

  const deleteSelectedItems = async () => {
    if (selectedItems.length === 0) return;
    try {
      await Promise.all(
        selectedItems.map((item) => deleteCatalogItem.mutateAsync({ kind, id: item.id })),
      );
      setSelectedIds((current) => {
        const next = new Set(current);
        for (const item of selectedItems) {
          next.delete(item.id);
        }
        return next;
      });
      toast.success(t("settings.freezoneCatalog.deleted"));
    } catch {
      toast.error(t("settings.freezoneCatalog.deleteFailed"));
    }
  };

  const exportItems = () => {
    const payloads = selectedItems.length > 0 ? selectedItems : catalogItems;
    if (payloads.length === 0) return;
    const exportPayload = payloads.length === 1
      ? stripCatalogMetadata(payloads[0].payload)
      : payloads.map((item) => stripCatalogMetadata(item.payload));
    downloadJson(
      exportPayload,
      `freezone-${kind}-${new Date().toISOString().slice(0, 10)}.json`,
    );
    toast.success(t("settings.freezoneCatalog.exported"));
  };

  const toggleAllSelected = (checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      for (const item of catalogItems) {
        if (checked) {
          next.add(item.id);
        } else {
          next.delete(item.id);
        }
      }
      return next;
    });
  };

  const toggleSelected = (id: string, checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  };

  const handleImportFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text()) as unknown;
      const payloads = Array.isArray(parsed) ? parsed : [parsed];
      const normalizedPayloads = payloads.map((payload) => {
        if (!isPlainObject(payload)) throw new Error("invalid json");
        return payload as FreezoneAgentConfigPayload;
      });
      if (!normalizedPayloads.every((payload) => validateCatalogPayload(kind, payload))) {
        throw new Error("invalid catalog payload");
      }
      for (const payload of normalizedPayloads) {
        await saveCatalogItem.mutateAsync({
          kind,
          payload,
        });
      }
      toast.success(t("settings.freezoneCatalog.imported"));
    } catch {
      toast.error(t("settings.freezoneCatalog.importFailed"));
    } finally {
      if (importInputRef.current) {
        importInputRef.current.value = "";
      }
    }
  };

  return (
    <>
      <section className="px-5 py-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="font-heading text-sm font-medium text-foreground">
              {t(isSkills ? "settings.tabs.freezoneSkills" : "settings.tabs.freezoneRecipes")}
            </h3>
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
              {t(
                isSkills
                  ? "settings.freezoneCatalog.skills.description"
                  : "settings.freezoneCatalog.recipes.description",
              )}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <input
              ref={importInputRef}
              type="file"
              accept=".json,application/json"
              aria-label={t("settings.freezoneCatalog.import")}
              className="hidden"
              onChange={(event) => {
                void handleImportFile(event.target.files?.[0]);
              }}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => importInputRef.current?.click()}
            >
              <Download className="size-3.5" />
              {t("settings.freezoneCatalog.import")}
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => {
                if (isSkills) {
                  setEditingSkill(null);
                  setAddingSkill(true);
                  return;
                }
                setEditingRecipe(null);
                setAddingRecipe(true);
              }}
            >
              <Plus className="size-3.5" />
              {t("settings.freezoneCatalog.new")}
            </Button>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t(
                isSkills
                  ? "settings.freezoneCatalog.searchSkills"
                  : "settings.freezoneCatalog.searchRecipes",
              )}
              className="h-9 rounded-md border-input/80 pl-9 focus-visible:border-ring/70 focus-visible:ring-1 focus-visible:ring-ring/30"
            />
          </div>
          <span className="shrink-0 text-[11px] text-muted-foreground">
            {t(
              isSkills
                ? "settings.freezoneCatalog.skillsCount"
                : "settings.freezoneCatalog.recipesCount",
              { count: itemCount },
            )}
          </span>
        </div>

        <CatalogSelectionBar
          allSelected={allVisibleSelected}
          count={itemCount}
          selectedCount={selectedCount}
          label={t("settings.freezoneCatalog.selectAll")}
          onDeleteSelected={() => void deleteSelectedItems()}
          onExport={exportItems}
          onToggleAll={toggleAllSelected}
        />
        <CatalogList
          kind={kind}
          items={catalogItems}
          loading={catalogQuery.isLoading}
          error={catalogQuery.isError}
          selectedIds={selectedIds}
          onRetry={() => void catalogQuery.refetch()}
          onToggleEnabled={(item, enabled) => void toggleItemEnabled(item, enabled)}
          onToggleSelected={toggleSelected}
          onEdit={(item) => {
            if (kind === "skills") {
              setAddingSkill(false);
              setEditingSkill(item.payload);
              return;
            }
            setAddingRecipe(false);
            setEditingRecipe(item.payload);
          }}
          onDelete={(item) => void deleteItem(item)}
        />
      </section>
      <NewSkillEditor
        open={addingSkill || editingSkill !== null}
        initialPayload={editingSkill}
        onOpenChange={(open) => {
          setAddingSkill(open);
          if (!open) setEditingSkill(null);
        }}
        onSave={saveItem}
        saving={saveCatalogItem.isPending}
      />
      <NewRecipeEditor
        open={addingRecipe || editingRecipe !== null}
        initialPayload={editingRecipe}
        onOpenChange={(open) => {
          setAddingRecipe(open);
          if (!open) setEditingRecipe(null);
        }}
        onSave={saveItem}
        saving={saveCatalogItem.isPending}
      />
    </>
  );
}

function NewRecipeEditor({
  initialPayload,
  open,
  onOpenChange,
  onSave,
  saving,
}: {
  initialPayload: FreezoneAgentConfigPayload | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (payload: FreezoneAgentConfigPayload) => Promise<void>;
  saving: boolean;
}) {
  const { t } = useTranslation();
  const [recipeDraft, setRecipeDraft] = useState<RecipeDraft>({
    id: "",
    name: "",
    outputKind: "image",
    actionKeys: [],
    systemPrompt: "",
    mustHaveItems: [],
    planningPrompt: "",
    resultSummary: "",
    sourceMediaRequired: false,
    forceEnhancement: false,
  });
  const [rawJsonOpen, setRawJsonOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    setRecipeDraft(recipeDraftFromPayload(initialPayload));
    setRawJsonOpen(false);
  }, [initialPayload, open]);

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setRecipeDraft({
        id: "",
        name: "",
        outputKind: "image",
        actionKeys: [],
        systemPrompt: "",
        mustHaveItems: [],
        planningPrompt: "",
        resultSummary: "",
        sourceMediaRequired: false,
        forceEnhancement: false,
      });
      setRawJsonOpen(false);
    }
    onOpenChange(nextOpen);
  };

  const updateRecipeDraft = (patch: Partial<RecipeDraft>) => {
    setRecipeDraft((draft) => ({ ...draft, ...patch }));
  };

  const rawRecipeJson = useMemo(
    () => ({
      ...(initialPayload ?? {}),
      result_summary: recipeDraft.resultSummary,
      planning_prompt: recipeDraft.planningPrompt,
      action_keys: recipeDraft.actionKeys,
      id: recipeDraft.id,
      must_have_items: recipeDraft.mustHaveItems,
      system_prompt: recipeDraft.systemPrompt,
      requires_source_media: recipeDraft.sourceMediaRequired,
      output_kind: recipeDraft.outputKind,
      name: recipeDraft.name,
      force_enhancement: recipeDraft.forceEnhancement,
    }),
    [initialPayload, recipeDraft],
  );
  const rawRecipeJsonText = useMemo(
    () => JSON.stringify(rawRecipeJson, null, 2),
    [rawRecipeJson],
  );
  const canSave = isValidRecipeDraft(recipeDraft) && !saving;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="grid h-[min(86vh,704px)] grid-rows-[auto_minmax(0,1fr)_auto] gap-0 overflow-hidden rounded-lg border border-border bg-black p-0 text-foreground ring-0 sm:max-w-[720px]"
        overlayClassName="bg-black/35"
      >
        <DialogHeader className="flex-row items-center justify-between gap-4 border-b border-border px-6 py-5">
          <DialogTitle className="text-lg font-semibold text-foreground">
            {t("settings.freezoneCatalog.newRecipe.title")}
          </DialogTitle>
          <button
            type="button"
            aria-label={t("settings.freezoneCatalog.newRecipe.close")}
            onClick={() => handleOpenChange(false)}
            className="grid size-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </DialogHeader>

        <div className="min-h-0 overflow-y-auto px-6 py-5">
          <div className="grid gap-3 md:grid-cols-2">
            <EditorField
              required
              label={t("settings.freezoneCatalog.newRecipe.id")}
              placeholder="my-recipe"
              value={recipeDraft.id}
              onChange={(value) => updateRecipeDraft({ id: value })}
              hint={t("settings.freezoneCatalog.newRecipe.idHint")}
            />
            <EditorField
              required
              label={t("settings.freezoneCatalog.newRecipe.name")}
              placeholder={t("settings.freezoneCatalog.newRecipe.namePlaceholder")}
              value={recipeDraft.name}
              onChange={(value) => updateRecipeDraft({ name: value })}
            />
          </div>

          <div className="mt-4 max-w-28">
            <EditorLabel required>
              {t("settings.freezoneCatalog.newRecipe.outputKind")}
            </EditorLabel>
            <Select
              value={recipeDraft.outputKind}
              onValueChange={(value) =>
                updateRecipeDraft({ outputKind: value as RecipeGenerationType })
              }
            >
              <SelectTrigger className="h-9 w-full rounded-md border-input/80 bg-input/20 text-foreground focus-visible:ring-1 focus-visible:ring-ring/30">
                <SelectValue />
              </SelectTrigger>
              <SelectContent align="start" className="min-w-28">
                {(["image", "video", "audio", "text"] as const).map((type) => (
                  <SelectItem key={type} value={type}>
                    {t(`settings.freezoneCatalog.newRecipe.outputKinds.${type}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <EditorFieldGroup>
            <TagInputField
              required
              label={t("settings.freezoneCatalog.newRecipe.actionKeys")}
              placeholder={t("settings.freezoneCatalog.newRecipe.actionKeysPlaceholder")}
              value={recipeDraft.actionKeys}
              onChange={(value) => updateRecipeDraft({ actionKeys: value })}
              hint={t("settings.freezoneCatalog.newRecipe.actionKeysHint")}
            />
          </EditorFieldGroup>

          <EditorFieldGroup>
            <EditorTextarea
              required
              label={t("settings.freezoneCatalog.newRecipe.systemPrompt")}
              placeholder={t("settings.freezoneCatalog.newRecipe.systemPromptPlaceholder")}
              value={recipeDraft.systemPrompt}
              onChange={(value) => updateRecipeDraft({ systemPrompt: value })}
              className="min-h-36"
            />
          </EditorFieldGroup>

          <EditorFieldGroup>
            <TagInputField
              label={t("settings.freezoneCatalog.newRecipe.mustHaveItems")}
              placeholder={t("settings.freezoneCatalog.newRecipe.mustHaveItemsPlaceholder")}
              value={recipeDraft.mustHaveItems}
              onChange={(value) => updateRecipeDraft({ mustHaveItems: value })}
              hint={t("settings.freezoneCatalog.newRecipe.mustHaveItemsHint")}
            />
            <EditorField
              label={t("settings.freezoneCatalog.newRecipe.planningPrompt")}
              placeholder={t("settings.freezoneCatalog.newRecipe.planningPromptPlaceholder")}
              value={recipeDraft.planningPrompt}
              onChange={(value) => updateRecipeDraft({ planningPrompt: value })}
            />
            <EditorField
              label={t("settings.freezoneCatalog.newRecipe.resultSummary")}
              placeholder={t("settings.freezoneCatalog.newRecipe.resultSummaryPlaceholder")}
              value={recipeDraft.resultSummary}
              onChange={(value) => updateRecipeDraft({ resultSummary: value })}
            />
            <ToggleRow
              label={t("settings.freezoneCatalog.newRecipe.sourceMediaRequired")}
              hint={t("settings.freezoneCatalog.newRecipe.sourceMediaRequiredHint")}
              checked={recipeDraft.sourceMediaRequired}
              onChange={(value) => updateRecipeDraft({ sourceMediaRequired: value })}
            />
            <ToggleRow
              label={t("settings.freezoneCatalog.newRecipe.forceEnhancement")}
              hint={t("settings.freezoneCatalog.newRecipe.forceEnhancementHint")}
              checked={recipeDraft.forceEnhancement}
              onChange={(value) => updateRecipeDraft({ forceEnhancement: value })}
            />
          </EditorFieldGroup>

          <RawJsonDisclosure
            open={rawJsonOpen}
            onOpenChange={setRawJsonOpen}
            label={t("settings.freezoneCatalog.newRecipe.rawJson")}
            collapseLabel={t("settings.freezoneCatalog.newRecipe.collapseRawJson")}
            ariaLabel={t("settings.freezoneCatalog.newRecipe.rawJsonAria")}
            hint={t("settings.freezoneCatalog.newRecipe.rawJsonSyncHint")}
            jsonText={rawRecipeJsonText}
          />
        </div>

        <DialogFooter className="border-t border-border bg-black px-6 py-4">
          <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
            {t("settings.freezoneCatalog.newRecipe.cancel")}
          </Button>
          <Button
            type="button"
            disabled={!canSave}
            onClick={() => {
              void onSave(rawRecipeJson);
            }}
          >
            {t("settings.freezoneCatalog.newRecipe.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function NewSkillEditor({
  initialPayload,
  open,
  onOpenChange,
  onSave,
  saving,
}: {
  initialPayload: FreezoneAgentConfigPayload | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (payload: FreezoneAgentConfigPayload) => Promise<void>;
  saving: boolean;
}) {
  const { t } = useTranslation();
  const [skillDraft, setSkillDraft] = useState<SkillDraft>({
    id: "",
    category: "general",
    description: "",
    keywords: [],
    nodeScopes: [],
    planningNotes: "",
    promptGuide: "",
    conductRules: "",
    qualityThreshold: "",
    domainConstraints: "",
  });
  const [ratingBands, setRatingBands] = useState<RatingBandDraft[]>([]);
  const [visualReviewItems, setVisualDimensions] = useState<DimensionDraft[]>([]);
  const [textReviewItems, setTextDimensions] = useState<DimensionDraft[]>([]);
  const [rawJsonOpen, setRawJsonOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const hydrated = skillDraftFromPayload(initialPayload);
    setSkillDraft(hydrated.draft);
    setRatingBands(hydrated.ratingBands);
    setVisualDimensions(hydrated.visualReviewItems);
    setTextDimensions(hydrated.textReviewItems);
    setRawJsonOpen(false);
  }, [initialPayload, open]);

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setSkillDraft({
        id: "",
        category: "general",
        description: "",
        keywords: [],
        nodeScopes: [],
        planningNotes: "",
        promptGuide: "",
        conductRules: "",
        qualityThreshold: "",
        domainConstraints: "",
      });
      setRatingBands([]);
      setVisualDimensions([]);
      setTextDimensions([]);
      setRawJsonOpen(false);
    }
    onOpenChange(nextOpen);
  };

  const updateSkillDraft = (patch: Partial<SkillDraft>) => {
    setSkillDraft((draft) => ({ ...draft, ...patch }));
  };

  const addRatingBand = () => {
    setRatingBands((items) => [
      ...items,
      { id: getNextDraftId(items), score: "0", description: "" },
    ]);
  };

  const updateRatingBand = (id: number, patch: Partial<Omit<RatingBandDraft, "id">>) => {
    setRatingBands((items) =>
      items.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    );
  };

  const addDimension = (
    setItems: Dispatch<SetStateAction<DimensionDraft[]>>,
  ) => {
    setItems((items) => [
      ...items,
      { id: getNextDraftId(items), name: "", weight: "1", description: "" },
    ]);
  };

  const updateDimension =
    (setItems: Dispatch<SetStateAction<DimensionDraft[]>>) =>
    (id: number, patch: Partial<Omit<DimensionDraft, "id">>) => {
      setItems((items) =>
        items.map((item) => (item.id === id ? { ...item, ...patch } : item)),
      );
    };

  const rawSkillJson = useMemo(
    () => ({
      ...(initialPayload ?? {}),
      id: skillDraft.id,
      description: skillDraft.description,
      category: skillDraft.category || "general",
      triggers: {
        keywords: skillDraft.keywords,
        node_scopes: skillDraft.nodeScopes,
      },
      planning: {
        planning_notes: skillDraft.planningNotes,
        prompt_guide: skillDraft.promptGuide,
        conduct_rules: splitDraftList(skillDraft.conductRules),
      },
      evaluation: {
        rating_bands: ratingBands.map((anchor) => ({
          score: parseNumericDraft(anchor.score, 0),
          description: anchor.description,
        })),
        visual_review_items: visualReviewItems.map((dimension) => ({
          name: dimension.name,
          weight: parseNumericDraft(dimension.weight, 1),
          description: dimension.description,
        })),
        text_review_items: textReviewItems.map((dimension) => ({
          name: dimension.name,
          weight: parseNumericDraft(dimension.weight, 1),
          description: dimension.description,
        })),
        quality_threshold: parseOptionalNumericDraft(skillDraft.qualityThreshold),
        domain_constraints: splitDraftList(skillDraft.domainConstraints),
      },
    }),
    [initialPayload, ratingBands, skillDraft, textReviewItems, visualReviewItems],
  );
  const rawSkillJsonText = useMemo(() => JSON.stringify(rawSkillJson, null, 2), [rawSkillJson]);
  const canSave = isValidSkillDraft(skillDraft) && !saving;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="grid h-[min(86vh,704px)] grid-rows-[auto_minmax(0,1fr)_auto] gap-0 overflow-hidden rounded-lg border border-border bg-black p-0 text-foreground ring-0 sm:max-w-[720px]"
        overlayClassName="bg-black/35"
      >
        <DialogHeader className="flex-row items-center justify-between gap-4 border-b border-border px-6 py-5">
          <DialogTitle className="text-lg font-semibold text-foreground">
            {t("settings.freezoneCatalog.newSkill.title")}
          </DialogTitle>
          <button
            type="button"
            aria-label={t("settings.freezoneCatalog.newSkill.close")}
            onClick={() => handleOpenChange(false)}
            className="grid size-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </DialogHeader>

        <div className="min-h-0 overflow-y-auto px-6 py-5">
          <div className="grid gap-3 md:grid-cols-3">
            <EditorField
              required
              label={t("settings.freezoneCatalog.newSkill.id")}
              placeholder="my-skill"
              value={skillDraft.id}
              onChange={(value) => updateSkillDraft({ id: value })}
              hint={t("settings.freezoneCatalog.newSkill.idHint")}
            />
            <EditorField
              required
              label={t("settings.freezoneCatalog.newSkill.category")}
              placeholder="general"
              value={skillDraft.category}
              onChange={(value) => updateSkillDraft({ category: value })}
            />
            <EditorField
              required
              label={t("settings.freezoneCatalog.newSkill.description")}
              placeholder={t("settings.freezoneCatalog.newSkill.descriptionPlaceholder")}
              value={skillDraft.description}
              onChange={(value) => updateSkillDraft({ description: value })}
            />
          </div>

          <EditorSection
            title={t("settings.freezoneCatalog.newSkill.triggerTitle")}
            description={t("settings.freezoneCatalog.newSkill.triggerDescription")}
          >
            <TagInputField
              required
              label={t("settings.freezoneCatalog.newSkill.keywords")}
              placeholder={t("settings.freezoneCatalog.newSkill.keywordsPlaceholder")}
              value={skillDraft.keywords}
              onChange={(value) => updateSkillDraft({ keywords: value })}
              hint={t("settings.freezoneCatalog.newSkill.keywordsHint")}
            />
            <TagInputField
              label={t("settings.freezoneCatalog.newSkill.nodeScopes")}
              placeholder={t("settings.freezoneCatalog.newSkill.nodeScopesPlaceholder")}
              value={skillDraft.nodeScopes}
              onChange={(value) => updateSkillDraft({ nodeScopes: value })}
            />
          </EditorSection>

          <EditorSection
            title={t("settings.freezoneCatalog.newSkill.planningTitle")}
            description={t("settings.freezoneCatalog.newSkill.planningDescription")}
          >
            <EditorTextarea
              label={t("settings.freezoneCatalog.newSkill.planningNotes")}
              placeholder={t("settings.freezoneCatalog.newSkill.planningNotesPlaceholder")}
              value={skillDraft.planningNotes}
              onChange={(value) => updateSkillDraft({ planningNotes: value })}
            />
            <EditorTextarea
              label={t("settings.freezoneCatalog.newSkill.promptGuide")}
              placeholder={t("settings.freezoneCatalog.newSkill.promptGuidePlaceholder")}
              value={skillDraft.promptGuide}
              onChange={(value) => updateSkillDraft({ promptGuide: value })}
            />
            <EditorField
              label={t("settings.freezoneCatalog.newSkill.conductRules")}
              placeholder={t("settings.freezoneCatalog.newSkill.conductRulesPlaceholder")}
              value={skillDraft.conductRules}
              onChange={(value) => updateSkillDraft({ conductRules: value })}
            />
            <PairField
              label={t("settings.freezoneCatalog.newSkill.aspectPresets")}
              leftPlaceholder={t("settings.freezoneCatalog.newSkill.modelNamePlaceholder")}
              rightPlaceholder={t("settings.freezoneCatalog.newSkill.ratioPlaceholder")}
            />
            <PairField
              label={t("settings.freezoneCatalog.newSkill.modelHints")}
              leftPlaceholder={t("settings.freezoneCatalog.newSkill.taskTypePlaceholder")}
              rightPlaceholder={t("settings.freezoneCatalog.newSkill.modelNameOnlyPlaceholder")}
            />
          </EditorSection>

          <EditorSection
            title={t("settings.freezoneCatalog.newSkill.evaluationTitle")}
            description={t("settings.freezoneCatalog.newSkill.evaluationDescription")}
          >
            <EditorField
              label={t("settings.freezoneCatalog.newSkill.qualityThreshold")}
              placeholder={t("settings.freezoneCatalog.newSkill.qualityThresholdPlaceholder")}
              className="max-w-[320px]"
              value={skillDraft.qualityThreshold}
              onChange={(value) => updateSkillDraft({ qualityThreshold: value })}
            />
            <EditorField
              label={t("settings.freezoneCatalog.newSkill.domainConstraints")}
              placeholder={t("settings.freezoneCatalog.newSkill.domainConstraintsPlaceholder")}
              value={skillDraft.domainConstraints}
              onChange={(value) => updateSkillDraft({ domainConstraints: value })}
            />
            <RatingBandsField
              anchors={ratingBands}
              onAdd={addRatingBand}
              onChange={updateRatingBand}
              onRemove={(id) =>
                setRatingBands((items) => items.filter((item) => item.id !== id))
              }
            />
            <DimensionListField
              label={t("settings.freezoneCatalog.newSkill.visualReviewItems")}
              dimensions={visualReviewItems}
              onAdd={() => addDimension(setVisualDimensions)}
              onChange={updateDimension(setVisualDimensions)}
              onRemove={(id) =>
                setVisualDimensions((items) => items.filter((item) => item.id !== id))
              }
            />
            <DimensionListField
              label={t("settings.freezoneCatalog.newSkill.textReviewItems")}
              dimensions={textReviewItems}
              onAdd={() => addDimension(setTextDimensions)}
              onChange={updateDimension(setTextDimensions)}
              onRemove={(id) =>
                setTextDimensions((items) => items.filter((item) => item.id !== id))
              }
            />
          </EditorSection>

          <button
            type="button"
            aria-label={t(
              rawJsonOpen
                ? "settings.freezoneCatalog.newSkill.collapseRawJson"
                : "settings.freezoneCatalog.newSkill.rawJson",
            )}
            aria-expanded={rawJsonOpen}
            onClick={() => setRawJsonOpen((value) => !value)}
            className="mt-4 flex items-center gap-2 border-t border-border pt-3 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            <span className="font-mono">{`{}`}</span>
            <ChevronDown
              className={cn("size-3 transition-transform", rawJsonOpen ? "rotate-180" : "")}
            />
            <span>
              {t(
                rawJsonOpen
                  ? "settings.freezoneCatalog.newSkill.collapseRawJson"
                  : "settings.freezoneCatalog.newSkill.rawJson",
              )}
            </span>
          </button>
          {rawJsonOpen ? (
            <div className="mt-2">
              <pre
                aria-label={t("settings.freezoneCatalog.newSkill.rawJsonAria")}
                className="max-h-72 overflow-auto rounded-md border border-border/70 bg-white/[0.025] p-3 font-mono text-xs leading-relaxed text-foreground"
              >
                {rawSkillJsonText}
              </pre>
              <p className="mt-2 text-[10px] text-muted-foreground">
                {t("settings.freezoneCatalog.newSkill.rawJsonSyncHint")}
              </p>
            </div>
          ) : null}
        </div>

        <DialogFooter className="border-t border-border bg-black px-6 py-4">
          <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
            {t("settings.freezoneCatalog.newSkill.cancel")}
          </Button>
          <Button
            type="button"
            disabled={!canSave}
            onClick={() => {
              void onSave(rawSkillJson);
            }}
          >
            {t("settings.freezoneCatalog.newSkill.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function getNextDraftId(items: Array<{ id: number }>) {
  return Math.max(0, ...items.map((item) => item.id)) + 1;
}

function recipeDraftFromPayload(payload: FreezoneAgentConfigPayload | null): RecipeDraft {
  return {
    id: getString(payload?.id),
    name: getString(payload?.name),
    outputKind: isRecipeGenerationType(payload?.output_kind) ? payload.output_kind : "image",
    actionKeys: getStringArray(payload?.action_keys),
    systemPrompt: getString(payload?.system_prompt),
    mustHaveItems: getStringArray(payload?.must_have_items),
    planningPrompt: getString(payload?.planning_prompt),
    resultSummary: getString(payload?.result_summary),
    sourceMediaRequired: payload?.requires_source_media === true,
    forceEnhancement: payload?.force_enhancement === true,
  };
}

function skillDraftFromPayload(payload: FreezoneAgentConfigPayload | null): {
  draft: SkillDraft;
  ratingBands: RatingBandDraft[];
  visualReviewItems: DimensionDraft[];
  textReviewItems: DimensionDraft[];
} {
  const triggers = getRecord(payload?.triggers);
  const planning = getRecord(payload?.planning);
  const evaluation = getRecord(payload?.evaluation);
  return {
    draft: {
      id: getString(payload?.id),
      category: getString(payload?.category) || "general",
      description: getString(payload?.description),
      keywords: getStringArray(triggers.keywords),
      nodeScopes: getStringArray(triggers.node_scopes),
      planningNotes: getString(planning.planning_notes),
      promptGuide: getString(planning.prompt_guide),
      conductRules: getStringArray(planning.conduct_rules).join("\n"),
      qualityThreshold: optionalNumberText(evaluation.quality_threshold),
      domainConstraints: getStringArray(evaluation.domain_constraints).join("\n"),
    },
    ratingBands: getRecordArray(evaluation.rating_bands).map((item, index) => ({
      id: index + 1,
      score: optionalNumberText(item.score) || "0",
      description: getString(item.description),
    })),
    visualReviewItems: getRecordArray(evaluation.visual_review_items).map((item, index) => ({
      id: index + 1,
      name: getString(item.name),
      weight: optionalNumberText(item.weight) || "1",
      description: getString(item.description),
    })),
    textReviewItems: getRecordArray(evaluation.text_review_items).map((item, index) => ({
      id: index + 1,
      name: getString(item.name),
      weight: optionalNumberText(item.weight) || "1",
      description: getString(item.description),
    })),
  };
}

function isRecipeGenerationType(value: unknown): value is RecipeGenerationType {
  return value === "image" || value === "video" || value === "audio" || value === "text";
}

function isValidSkillDraft(draft: SkillDraft) {
  return (
    draft.id.trim().length > 0 &&
    draft.category.trim().length > 0 &&
    draft.description.trim().length > 0 &&
    draft.keywords.some((keyword) => keyword.trim().length > 0)
  );
}

function isValidRecipeDraft(draft: RecipeDraft) {
  return (
    draft.id.trim().length > 0 &&
    draft.name.trim().length > 0 &&
    isRecipeGenerationType(draft.outputKind) &&
    draft.actionKeys.some((key) => key.trim().length > 0) &&
    draft.systemPrompt.trim().length > 0
  );
}

function validateCatalogPayload(kind: FreezoneCatalogKind, payload: FreezoneAgentConfigPayload) {
  if (kind === "skills") {
    const triggers = getRecord(payload.triggers);
    return (
      getString(payload.id).trim().length > 0 &&
      getString(payload.category).trim().length > 0 &&
      getString(payload.description).trim().length > 0 &&
      getStringArray(triggers.keywords).some((keyword) => keyword.trim().length > 0)
    );
  }
  return (
    getString(payload.id).trim().length > 0 &&
    getString(payload.name).trim().length > 0 &&
    isRecipeGenerationType(payload.output_kind) &&
    getStringArray(payload.action_keys).some((key) => key.trim().length > 0) &&
    getString(payload.system_prompt).trim().length > 0
  );
}

function optionalNumberText(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "";
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function getRecord(value: unknown): Record<string, unknown> {
  return isPlainObject(value) ? value : {};
}

function getRecordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function parseNumericDraft(value: string, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseOptionalNumericDraft(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return parseNumericDraft(trimmed, 0);
}

function splitDraftList(value: string) {
  return value
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function EditorSection({
  children,
  description,
  title,
}: {
  children: ReactNode;
  description?: string;
  title: string;
}) {
  return (
    <div className="mt-5 border-t border-border pt-4">
      <h4 className="text-xs font-medium text-foreground">{title}</h4>
      {description ? (
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{description}</p>
      ) : null}
      <div className="mt-3 space-y-3">{children}</div>
    </div>
  );
}

function EditorFieldGroup({ children }: { children: ReactNode }) {
  return <div className="mt-5 space-y-3 border-t border-border pt-4">{children}</div>;
}

function EditorLabel({ children, required }: { children: ReactNode; required?: boolean }) {
  return (
    <span className="mb-1.5 block text-xs font-medium text-foreground">
      {children}
      {required ? <span className="ml-1 text-destructive">*</span> : null}
    </span>
  );
}

function EditorField({
  className,
  defaultValue,
  hint,
  label,
  onChange,
  placeholder,
  required,
  value,
}: {
  className?: string;
  defaultValue?: string;
  hint?: string;
  label: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  value?: string;
}) {
  return (
    <label className={cn("block", className)}>
      <EditorLabel required={required}>{label}</EditorLabel>
      <Input
        defaultValue={value === undefined ? defaultValue : undefined}
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
        placeholder={placeholder}
        className="h-9 rounded-md border-input/80 bg-input/20 text-foreground placeholder:text-muted-foreground focus-visible:border-ring/70 focus-visible:ring-1 focus-visible:ring-ring/30"
      />
      {hint ? <span className="mt-1 block text-[10px] text-muted-foreground">{hint}</span> : null}
    </label>
  );
}

function TagInputField({
  hint,
  label,
  onChange,
  placeholder,
  required,
  value,
}: {
  hint?: string;
  label: string;
  onChange: (value: string[]) => void;
  placeholder?: string;
  required?: boolean;
  value: string[];
}) {
  const [draft, setDraft] = useState("");

  const addDraft = () => {
    const next = draft.trim();
    if (!next) return;
    onChange(value.includes(next) ? value : [...value, next]);
    setDraft("");
  };

  const removeTag = (tag: string) => {
    onChange(value.filter((item) => item !== tag));
  };

  return (
    <label className="block">
      <EditorLabel required={required}>{label}</EditorLabel>
      <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-input/80 bg-input/20 px-2 py-1 transition-colors focus-within:border-ring/70 focus-within:ring-1 focus-within:ring-ring/30">
        {value.map((tag) => (
          <span
            key={tag}
            className="inline-flex h-6 max-w-full items-center gap-1 rounded bg-white/[0.07] px-2 text-xs text-foreground"
          >
            <span className="truncate">{tag}</span>
            <button
              type="button"
              aria-label={`删除 ${tag}`}
              onClick={() => removeTag(tag)}
              className="grid size-3.5 shrink-0 place-items-center rounded text-muted-foreground transition-colors hover:text-foreground"
            >
              <X className="size-3" />
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addDraft();
              return;
            }
            if (event.key === "," || event.key === "，") {
              event.preventDefault();
              addDraft();
              return;
            }
            if ((event.key === "Backspace" || event.key === "Delete") && !draft && value.length) {
              event.preventDefault();
              onChange(value.slice(0, -1));
            }
          }}
          onBlur={addDraft}
          placeholder={value.length ? undefined : placeholder}
          className="h-6 min-w-24 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
        />
      </div>
      {hint ? <span className="mt-1 block text-[10px] text-muted-foreground">{hint}</span> : null}
    </label>
  );
}

function EditorTextarea({
  className,
  label,
  onChange,
  placeholder,
  required,
  value,
}: {
  className?: string;
  label: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  value?: string;
}) {
  return (
    <label className="block">
      <EditorLabel required={required}>{label}</EditorLabel>
      <Textarea
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
        placeholder={placeholder}
        className={cn(
          "min-h-16 resize-y rounded-md border-input/80 bg-input/20 text-foreground placeholder:text-muted-foreground focus-visible:border-ring/70 focus-visible:ring-1 focus-visible:ring-ring/30",
          className,
        )}
      />
    </label>
  );
}

function ToggleRow({
  checked,
  hint,
  label,
  onChange,
}: {
  checked: boolean;
  hint?: string;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-4">
      <span className="min-w-0">
        <span className="block text-xs font-medium text-foreground">{label}</span>
        {hint ? (
          <span className="mt-1 block text-[10px] leading-relaxed text-muted-foreground">
            {hint}
          </span>
        ) : null}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative h-5 w-9 shrink-0 rounded-full border transition-colors",
          checked
            ? "border-transparent bg-[#111] dark:bg-white/[0.18]"
            : "border-transparent bg-black/[0.06] dark:bg-white/[0.08]",
        )}
      >
        <span
          className={cn(
            "absolute top-1/2 left-0.5 size-4 -translate-y-1/2 rounded-full bg-white shadow-sm transition-transform",
            checked ? "translate-x-4" : "translate-x-0",
          )}
        />
      </button>
    </label>
  );
}

function RawJsonDisclosure({
  ariaLabel,
  collapseLabel,
  hint,
  jsonText,
  label,
  onOpenChange,
  open,
}: {
  ariaLabel: string;
  collapseLabel: string;
  hint: string;
  jsonText: string;
  label: string;
  onOpenChange: (open: boolean) => void;
  open: boolean;
}) {
  return (
    <>
      <button
        type="button"
        aria-label={open ? collapseLabel : label}
        aria-expanded={open}
        onClick={() => onOpenChange(!open)}
        className="mt-4 flex items-center gap-2 border-t border-border pt-3 text-xs text-muted-foreground transition-colors hover:text-foreground"
      >
        <span className="font-mono">{`{}`}</span>
        <ChevronDown className={cn("size-3 transition-transform", open ? "rotate-180" : "")} />
        <span>{open ? collapseLabel : label}</span>
      </button>
      {open ? (
        <div className="mt-2">
          <pre
            aria-label={ariaLabel}
            className="max-h-72 overflow-auto rounded-md border border-border/70 bg-white/[0.025] p-3 font-mono text-xs leading-relaxed text-foreground"
          >
            {jsonText}
          </pre>
          <p className="mt-2 text-[10px] text-muted-foreground">{hint}</p>
        </div>
      ) : null}
    </>
  );
}

function PairField({
  label,
  leftPlaceholder,
  rightPlaceholder,
}: {
  label: string;
  leftPlaceholder: string;
  rightPlaceholder: string;
}) {
  return (
    <div>
      <EditorLabel>{label}</EditorLabel>
      <div className="grid grid-cols-[minmax(0,1fr)_20px_minmax(0,1fr)_28px] items-center gap-2">
        <Input
          placeholder={leftPlaceholder}
          className="h-9 rounded-md border-input/80 bg-input/20 text-foreground placeholder:text-muted-foreground focus-visible:border-ring/70 focus-visible:ring-1 focus-visible:ring-ring/30"
        />
        <span className="text-center text-muted-foreground">→</span>
        <Input
          placeholder={rightPlaceholder}
          className="h-9 rounded-md border-input/80 bg-input/20 text-foreground placeholder:text-muted-foreground focus-visible:border-ring/70 focus-visible:ring-1 focus-visible:ring-ring/30"
        />
        <button
          type="button"
          disabled
          aria-label="add"
          className="grid size-8 place-items-center rounded-md text-muted-foreground opacity-50"
        >
          <Plus className="size-4" />
        </button>
      </div>
    </div>
  );
}

function DimensionListField({
  dimensions,
  label,
  onAdd,
  onChange,
  onRemove,
}: {
  dimensions: DimensionDraft[];
  label: string;
  onAdd: () => void;
  onChange: (id: number, patch: Partial<Omit<DimensionDraft, "id">>) => void;
  onRemove: (id: number) => void;
}) {
  const { t } = useTranslation();

  return (
    <div>
      <EditorLabel>{label}</EditorLabel>
      <p className="mb-2 text-[10px] text-muted-foreground">
        {t("settings.freezoneCatalog.newSkill.dimensionWeightHint")}
      </p>
      <div className="space-y-2">
        {dimensions.map((dimension) => (
          <div
            key={dimension.id}
            className="rounded-md border border-border/70 bg-white/[0.015] p-2"
          >
            <div className="grid grid-cols-[minmax(0,1fr)_auto_56px_28px] items-center gap-2">
              <Input
                value={dimension.name}
                onChange={(event) =>
                  onChange(dimension.id, { name: event.target.value })
                }
                placeholder={t("settings.freezoneCatalog.newSkill.dimensionNamePlaceholder")}
                className="h-9 rounded-md border-input/80 bg-input/20 text-foreground placeholder:text-muted-foreground focus-visible:border-ring/70 focus-visible:ring-1 focus-visible:ring-ring/30"
              />
              <span className="text-[11px] text-muted-foreground">
                {t("settings.freezoneCatalog.newSkill.dimensionWeight")}
              </span>
              <Input
                type="number"
                min={0}
                max={1}
                step={0.1}
                value={dimension.weight}
                onChange={(event) =>
                  onChange(dimension.id, { weight: event.target.value })
                }
                placeholder={t("settings.freezoneCatalog.newSkill.dimensionWeightPlaceholder")}
                className="h-9 rounded-md border-input/80 bg-input/20 text-foreground placeholder:text-muted-foreground focus-visible:border-ring/70 focus-visible:ring-1 focus-visible:ring-ring/30"
              />
              <button
                type="button"
                aria-label={t("settings.freezoneCatalog.newSkill.removeDimension")}
                onClick={() => onRemove(dimension.id)}
                className="grid size-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            </div>
            <Input
              value={dimension.description}
              onChange={(event) =>
                onChange(dimension.id, { description: event.target.value })
              }
              placeholder={t("settings.freezoneCatalog.newSkill.dimensionDescriptionPlaceholder")}
              className="mt-2 h-9 rounded-md border-input/80 bg-input/20 text-foreground placeholder:text-muted-foreground focus-visible:border-ring/70 focus-visible:ring-1 focus-visible:ring-ring/30"
            />
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" onClick={onAdd}>
          <Plus className="size-3.5" />
          {t("settings.freezoneCatalog.newSkill.addDimension")}
        </Button>
      </div>
    </div>
  );
}

function RatingBandsField({
  anchors,
  onAdd,
  onChange,
  onRemove,
}: {
  anchors: RatingBandDraft[];
  onAdd: () => void;
  onChange: (id: number, patch: Partial<Omit<RatingBandDraft, "id">>) => void;
  onRemove: (id: number) => void;
}) {
  const { t } = useTranslation();

  return (
    <div>
      <EditorLabel>{t("settings.freezoneCatalog.newSkill.ratingBands")}</EditorLabel>
      <div className="space-y-2">
        {anchors.map((anchor) => (
          <div
            key={anchor.id}
            className="grid grid-cols-[64px_minmax(0,1fr)_28px] items-center gap-2"
          >
            <Input
              type="number"
              min={0}
              max={10}
              step={0.5}
              value={anchor.score}
              onChange={(event) => onChange(anchor.id, { score: event.target.value })}
              placeholder={t("settings.freezoneCatalog.newSkill.ratingBandScorePlaceholder")}
              className="h-9 rounded-md border-input/80 bg-input/20 text-foreground placeholder:text-muted-foreground focus-visible:border-ring/70 focus-visible:ring-1 focus-visible:ring-ring/30"
            />
            <Input
              value={anchor.description}
              onChange={(event) =>
                onChange(anchor.id, { description: event.target.value })
              }
              placeholder={t(
                "settings.freezoneCatalog.newSkill.ratingBandDescriptionPlaceholder",
              )}
              className="h-9 rounded-md border-input/80 bg-input/20 text-foreground placeholder:text-muted-foreground focus-visible:border-ring/70 focus-visible:ring-1 focus-visible:ring-ring/30"
            />
            <button
              type="button"
              aria-label={t("settings.freezoneCatalog.newSkill.removeRatingBand")}
              onClick={() => onRemove(anchor.id)}
              className="grid size-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" onClick={onAdd}>
          <Plus className="size-3.5" />
          {t("settings.freezoneCatalog.newSkill.addRatingBand")}
        </Button>
      </div>
    </div>
  );
}

interface ManagedCatalogItem {
  builtin: boolean;
  customized: boolean;
  enabled: boolean;
  id: string;
  payload: FreezoneAgentConfigPayload;
  title: string;
  description: string;
  tags: string[];
}

function downloadJson(payload: unknown, filename: string) {
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function CatalogSelectionBar({
  allSelected,
  count,
  label,
  onDeleteSelected,
  onExport,
  onToggleAll,
  selectedCount,
}: {
  allSelected: boolean;
  count: number;
  label: string;
  onDeleteSelected: () => void;
  onExport: () => void;
  onToggleAll: (checked: boolean) => void;
  selectedCount: number;
}) {
  const { t } = useTranslation();

  return (
    <div className="mt-3 flex h-9 items-center justify-between rounded-md border border-border/70 bg-white/[0.018] px-3">
      <label className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
        <Checkbox
          checked={allSelected}
          disabled={count === 0}
          onCheckedChange={(checked) => onToggleAll(checked === true)}
        />
        <span>{label}</span>
        <span>
          {t("settings.freezoneCatalog.selectionCount", { count, selectedCount })}
        </span>
      </label>
      <div className="flex items-center gap-2">
        {selectedCount > 0 ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 px-2 text-xs text-destructive hover:text-destructive"
            onClick={onDeleteSelected}
          >
            <Trash2 className="size-3.5" />
            {t("settings.freezoneCatalog.deleteSelected")}
          </Button>
        ) : null}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={count === 0}
          className="h-7 px-2 text-xs"
          onClick={onExport}
        >
          <Upload className="size-3.5" />
          {t("settings.freezoneCatalog.export")}
        </Button>
      </div>
    </div>
  );
}

function CatalogList({
  error,
  items,
  kind,
  loading,
  onDelete,
  onEdit,
  onRetry,
  onToggleEnabled,
  onToggleSelected,
  selectedIds,
}: {
  error: boolean;
  items: ManagedCatalogItem[];
  kind: FreezoneCatalogKind;
  loading: boolean;
  onDelete: (item: ManagedCatalogItem) => void;
  onEdit: (item: ManagedCatalogItem) => void;
  onRetry: () => void;
  onToggleEnabled: (item: ManagedCatalogItem, enabled: boolean) => void;
  onToggleSelected: (id: string, checked: boolean) => void;
  selectedIds: Set<string>;
}) {
  const { t } = useTranslation();

  if (loading) {
    return (
      <div className="mt-2 rounded-md border border-border/70 px-4 py-12 text-center text-sm text-muted-foreground">
        {t("settings.freezoneCatalog.loading")}
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-2 rounded-md border border-border/70 px-4 py-12 text-center">
        <p className="text-sm font-medium text-foreground">
          {t("settings.freezoneCatalog.loadFailed")}
        </p>
        <Button type="button" variant="outline" size="sm" className="mt-3" onClick={onRetry}>
          {t("settings.freezoneCatalog.retry")}
        </Button>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="mt-2 rounded-md border border-border/70 px-4 py-12 text-center">
        <p className="text-sm font-medium text-foreground">
          {t(
            kind === "skills"
              ? "settings.freezoneCatalog.emptySkills"
              : "settings.freezoneCatalog.emptyRecipes",
          )}
        </p>
        <p className="mx-auto mt-2 max-w-[420px] text-xs leading-relaxed text-muted-foreground">
          {t("settings.freezoneCatalog.emptyDescription")}
        </p>
      </div>
    );
  }

  return (
    <div className="mt-2 space-y-2">
      {items.map((item) => (
        <article
          key={item.id}
          className={cn(
            "flex items-center gap-3 rounded-md border border-border/70 bg-white/[0.015] px-3 py-2.5 transition-opacity",
            item.enabled ? "" : "opacity-55",
          )}
        >
          <Checkbox
            checked={selectedIds.has(item.id)}
            onCheckedChange={(checked) => onToggleSelected(item.id, checked === true)}
          />
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2">
              <h4 className="truncate font-mono text-[13px] font-semibold text-foreground">
                {item.id}
              </h4>
              {item.builtin ? (
                <span className="shrink-0 rounded border border-border/70 px-1.5 py-0.5 text-[10px] leading-none text-muted-foreground">
                  {t("settings.freezoneCatalog.builtIn")}
                </span>
              ) : null}
              {item.customized ? (
                <span className="shrink-0 rounded border border-cyan-500/40 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] leading-none text-cyan-200">
                  {t("settings.freezoneCatalog.customized")}
                </span>
              ) : null}
            </div>
            <p className="mt-1 truncate text-[11px] text-muted-foreground">{item.description}</p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              role="switch"
              aria-checked={item.enabled}
              aria-label={t("settings.freezoneCatalog.toggleEnabled", { id: item.id })}
              onClick={() => onToggleEnabled(item, !item.enabled)}
              className={cn(
                "relative h-4 w-7 rounded-full border transition-colors",
                item.enabled
                  ? "border-transparent bg-[#111] dark:bg-white/[0.18]"
                  : "border-transparent bg-black/[0.06] dark:bg-white/[0.08]",
              )}
            >
              <span
                className={cn(
                  "absolute top-1/2 left-0.5 size-3 -translate-y-1/2 rounded-full bg-white transition-transform",
                  item.enabled ? "translate-x-3" : "translate-x-0",
                )}
              />
            </button>
            <button
              type="button"
              aria-label={t("settings.freezoneCatalog.editItem", { id: item.id })}
              onClick={() => onEdit(item)}
              className="grid size-7 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground"
            >
              <Pencil className="size-3.5" />
            </button>
            <button
              type="button"
              aria-label={t("settings.freezoneCatalog.deleteItem", { id: item.id })}
              onClick={() => onDelete(item)}
              className="grid size-7 place-items-center rounded-md text-destructive transition-colors hover:bg-destructive/10"
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

function toManagedCatalogItem(
  item: FreezoneAgentConfigPayload,
  kind: FreezoneCatalogKind,
): ManagedCatalogItem {
  const id = typeof item.id === "string" ? item.id : "";
  if (kind === "recipes") {
    return {
      builtin: item._catalog_source === "builtin",
      customized: item._catalog_source === "user" && item._catalog_base_source === "builtin",
      enabled: item.enabled !== false,
      id,
      payload: item,
      title: typeof item.name === "string" ? item.name : id,
      description:
        getString(item.result_summary) ||
        getString(item.planning_prompt) ||
        getString(item.system_prompt),
      tags: [getString(item.output_kind), ...getStringArray(item.action_keys)].filter(Boolean),
    };
  }
  const triggers = typeof item.triggers === "object" && item.triggers ? item.triggers : {};
  return {
    builtin: item._catalog_source === "builtin",
    customized: item._catalog_source === "user" && item._catalog_base_source === "builtin",
    enabled: item.enabled !== false,
    id,
    payload: item,
    title: id,
    description: getString(item.description),
    tags: [
      getString(item.category),
      ...getStringArray((triggers as Record<string, unknown>).keywords),
    ].filter(Boolean),
  };
}

function stripCatalogMetadata(payload: FreezoneAgentConfigPayload): FreezoneAgentConfigPayload {
  return Object.fromEntries(
    Object.entries(payload).filter(([key]) => !key.startsWith("_catalog_")),
  ) as FreezoneAgentConfigPayload;
}

function getString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function getStringArray(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}
