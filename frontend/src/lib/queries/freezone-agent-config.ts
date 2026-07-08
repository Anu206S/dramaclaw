// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiCall } from "@/api/client";

export type FreezoneAgentConfigKind = "skills" | "recipes";
export type FreezoneAgentConfigPayload = Record<string, unknown> & { id?: string };

export const freezoneAgentConfigQueryKey = (kind: FreezoneAgentConfigKind) => [
  "freezone-agent-config",
  kind,
];

export function useFreezoneAgentConfigItems(kind: FreezoneAgentConfigKind) {
  return useQuery({
    queryKey: freezoneAgentConfigQueryKey(kind),
    queryFn: () =>
      apiCall<FreezoneAgentConfigPayload[]>(`freezone/agent-config/${kind}`),
  });
}

export function useSaveFreezoneAgentConfigItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      kind,
      payload,
    }: {
      kind: FreezoneAgentConfigKind;
      payload: FreezoneAgentConfigPayload;
    }) =>
      apiCall<FreezoneAgentConfigPayload>(`freezone/agent-config/${kind}`, {
        method: "POST",
        json: payload,
      }),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: freezoneAgentConfigQueryKey(variables.kind),
      });
    },
  });
}

export function useDeleteFreezoneAgentConfigItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      kind,
    }: {
      id: string;
      kind: FreezoneAgentConfigKind;
    }) =>
      apiCall<{ deleted: boolean }>(
        `freezone/agent-config/${kind}/${encodeURIComponent(id)}`,
        { method: "DELETE" },
      ),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: freezoneAgentConfigQueryKey(variables.kind),
      });
    },
  });
}
