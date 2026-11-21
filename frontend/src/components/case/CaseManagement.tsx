"use client";

import { useCallback, useMemo } from "react";
import { ActingAs } from "@/components/ActingAs";
import { useSessionUser } from "@/components/AuthProvider";
import { HandoffManager, OutcomeView } from "@/components/handoff/HandoffManager";
import { Button } from "@/components/ui/Button";
import { useActor } from "@/hooks/useActor";
import { useManagedCase } from "@/hooks/useManagedCase";
import { usePolling } from "@/hooks/usePolling";
import { createDemoApi } from "@/lib/api";
import { useT } from "@/lib/i18n/LanguageProvider";
import type { CasePage } from "@/lib/types/handoff";

type Props = { caseId: string; status: string; onChanged: () => Promise<void> };

/** The server decides management rights, including ward scope; nurses never get the action. */
export function CaseManagement(props: Props) {
  const me = useSessionUser();
  if (me?.role === "staff") return null;
  return <ManagerControls key={me?.staff_id ?? "demo"} {...props} />;
}

function ManagerControls({ caseId, status, onChanged }: Props) {
  const t = useT();
  const [actorId, setActorId] = useActor();
  const api = useMemo(() => createDemoApi(actorId), [actorId]);
  const load = useCallback((signal: AbortSignal) => api<CasePage>(
    `/cases/search?q=${caseId}&page=1&page_size=100`, { signal },
  ), [api, caseId]);
  const handedOff = status === "MANUAL_HANDOFF";
  const { data, error, refresh } = usePolling(load, { enabled: handedOff });
  const managed = useManagedCase(data?.items, api);
  const own = data?.items?.find((row) => String(row.id) === caseId);
  const canManage = handedOff && own?.can_manage && !error;
  const changed = useCallback(async () => {
    await Promise.all([refresh(), onChanged()]);
  }, [refresh, onChanged]);

  return (
    <div className="space-y-3">
      {handedOff && (
        <div className="flex flex-wrap items-center gap-3">
          <ActingAs id="case-managing-as" value={actorId} onChange={(id) => {
            managed.reset();
            setActorId(id);
          }} />
          {canManage && <Button variant="primary" onClick={() => managed.open(own.id)}>{t("hand.manage")}</Button>}
        </div>
      )}
      {!managed.selected && <OutcomeView outcome={managed.outcome} />}
      {handedOff && managed.selected && (
        <HandoffManager
          key={`${actorId}:${caseId}`}
          caseId={managed.selected.id}
          api={api}
          onClose={managed.close}
          onDone={managed.done}
          onChanged={changed}
        />
      )}
    </div>
  );
}
