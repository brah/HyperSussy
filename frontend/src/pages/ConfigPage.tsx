import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { configQuery } from "../api/queries";
import { resetConfigField, updateConfigField } from "../api/client";
import { PageHeader } from "../components/layout/PageHeader";
import { PanelCard } from "../components/common/PanelCard";
import type { ConfigFieldItem } from "../api/types";

/**
 * Live-editable settings page.
 *
 * Only fields in the backend HOT_FIELDS registry (see
 * settings_service.py) are editable. Each edit PUTs the new value to
 * /api/config/{key} which validates it via Pydantic, mutates the
 * live settings instance the BackgroundRunner holds, and persists
 * an override row in SQLite.
 *
 * Engines, retention, and alerting all re-read settings every tick,
 * so changes here take effect on the next loop iteration without a
 * restart.
 */
export function ConfigPage() {
  const { data, isLoading, error } = useQuery(configQuery());

  const sections = useMemo(() => {
    if (!data) return [] as { section: string; fields: ConfigFieldItem[] }[];
    const groups = new Map<string, ConfigFieldItem[]>();
    for (const f of data.fields) {
      const bucket = groups.get(f.section) ?? [];
      bucket.push(f);
      groups.set(f.section, bucket);
    }
    return Array.from(groups.entries()).map(([section, fields]) => ({
      section,
      fields,
    }));
  }, [data]);

  return (
    <div>
      <PageHeader title="Config">
        <span className="text-xs text-hs-grey">
          Changes apply on the next engine tick. Persisted to SQLite.
        </span>
      </PageHeader>

      {isLoading && (
        <div className="text-hs-grey text-sm">Loading configuration…</div>
      )}
      {error && (
        <div className="text-hs-red text-sm">
          Failed to load configuration: {(error as Error).message}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {sections.map(({ section, fields }) => (
          <PanelCard key={section} title={section}>
            <div className="divide-y divide-hs-grid">
              {fields.map((field) => (
                <ConfigRow key={field.key} field={field} />
              ))}
            </div>
          </PanelCard>
        ))}
      </div>
    </div>
  );
}

interface ConfigRowProps {
  field: ConfigFieldItem;
}

/**
 * A single editable field row.
 *
 * Numeric inputs are debounced — the PUT fires 500ms after the last
 * keystroke so a user typing "0.25" doesn't issue 4 sequential
 * writes. Booleans commit immediately on toggle.
 */
function ConfigRow({ field }: Readonly<ConfigRowProps>) {
  const queryClient = useQueryClient();
  // Local "draft" value so typing doesn't immediately reflect the
  // server-reported value (which lags behind by one round-trip).
  const [draft, setDraft] = useState<string>(String(field.value));
  const [status, setStatus] = useState<"idle" | "saving" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string>("");

  // Reset the draft when the server value changes and we're idle
  // (e.g. another client wrote, or a reset happened). Intentionally
  // keyed on field.value only — status is a write-only dep here and
  // re-running when status transitions would undo an in-flight edit.
  useEffect(() => {
    if (status === "idle") {
      setDraft(String(field.value));
    }
  }, [field.value, status]);

  const updateMutation = useMutation({
    mutationFn: (value: number | boolean) =>
      updateConfigField(field.key, value),
    onMutate: () => {
      setStatus("saving");
      setErrorMsg("");
    },
    onSuccess: () => {
      setStatus("idle");
      void queryClient.invalidateQueries({ queryKey: ["config"] });
    },
    onError: (err: Error) => {
      setStatus("error");
      setErrorMsg(err.message);
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => resetConfigField(field.key),
    onMutate: () => {
      setStatus("saving");
      setErrorMsg("");
    },
    onSuccess: (item) => {
      setDraft(String(item.value));
      setStatus("idle");
      void queryClient.invalidateQueries({ queryKey: ["config"] });
    },
    onError: (err: Error) => {
      setStatus("error");
      setErrorMsg(err.message);
    },
  });

  // Debounced commit for numeric inputs. Boolean toggles bypass this
  // and commit immediately via handleBoolToggle below. The mutation
  // object is stable-enough across renders that including it as a
  // dep wouldn't retrigger the timer — React Query returns the same
  // instance per hook unless the queryClient itself changes.
  useEffect(() => {
    if (field.type === "bool") return;
    const parsed =
      field.type === "int"
        ? Number.parseInt(draft, 10)
        : Number.parseFloat(draft);
    if (Number.isNaN(parsed)) return;
    if (parsed === field.value) return;

    const handle = globalThis.setTimeout(() => {
      updateMutation.mutate(parsed);
    }, 500);
    return () => globalThis.clearTimeout(handle);
  }, [draft, field.type, field.value, updateMutation]);

  function handleBoolToggle() {
    // This handler is only wired up from the ``field.type === "bool"``
    // branch of the render below, so we can lean on the discriminated
    // union here and skip a runtime cast.
    if (field.type !== "bool") return;
    updateMutation.mutate(!field.value);
  }

  const overridden = field.overridden;
  const badge = overridden ? (
    <span className="text-[10px] uppercase tracking-wider text-hs-green">
      Custom
    </span>
  ) : (
    <span className="text-[10px] uppercase tracking-wider text-hs-grey">
      Default
    </span>
  );

  return (
    <div className="py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm text-hs-text font-medium">{field.label}</span>
            {badge}
          </div>
          <p className="text-xs text-hs-grey mt-0.5">{field.description}</p>
          <p className="text-[10px] text-hs-grey/70 font-mono mt-0.5">{field.key}</p>
        </div>

        <div className="flex flex-col items-end gap-1 shrink-0">
          {field.type === "bool" ? (
            <button
              onClick={handleBoolToggle}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                field.value
                  ? "bg-hs-mint text-hs-green border-hs-green"
                  : "bg-hs-surface text-hs-grey border-hs-grid"
              }`}
              disabled={status === "saving"}
            >
              {field.value ? "On" : "Off"}
            </button>
          ) : (
            <input
              type="number"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              step={field.type === "int" ? 1 : "any"}
              min={field.minimum ?? undefined}
              max={field.maximum ?? undefined}
              className="w-32 rounded-[10px] border border-hs-grid bg-hs-surface
                         px-2 py-1 text-xs text-hs-text font-mono tabular-nums
                         focus:border-hs-green focus:outline-none"
            />
          )}
          <div className="flex items-center gap-2">
            {overridden && (
              <button
                onClick={() => resetMutation.mutate()}
                className="text-[10px] text-hs-grey hover:text-hs-text"
                disabled={status === "saving"}
              >
                reset
              </button>
            )}
            <StatusIndicator status={status} errorMsg={errorMsg} />
          </div>
        </div>
      </div>
    </div>
  );
}

function StatusIndicator({
  status,
  errorMsg,
}: Readonly<{ status: "idle" | "saving" | "error"; errorMsg: string }>) {
  if (status === "saving") {
    return <span className="text-[10px] text-hs-grey">saving…</span>;
  }
  if (status === "error") {
    return (
      <span className="text-[10px] text-hs-red" title={errorMsg}>
        error
      </span>
    );
  }
  return null;
}
