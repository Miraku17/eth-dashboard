import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  createAlertRule,
  fetchAlertEvents,
  fetchAlertRules,
  patchAlertRule,
  type AlertEvent,
  type AlertRule,
  type AlertRuleInput,
} from "../api";
import { NEW_RULE_EVENT } from "../hooks/useGlobalShortcuts";
import { formatUsdCompact, relativeTime } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import Button from "./ui/Button";
import Card from "./ui/Card";
import Modal from "./ui/Modal";
import { useToast } from "./ui/Toaster";
import RuleForm from "./alerts/RuleForm";
import RulesList from "./alerts/RulesList";

const TYPE_STYLES: Record<string, string> = {
  price_above: "bg-up/10 text-up ring-up/20",
  price_below: "bg-down/10 text-down ring-down/20",
  price_change_pct: "bg-sky-500/10 text-sky-300 ring-sky-400/20",
  whale_transfer: "bg-brand/15 text-brand-soft ring-brand/20",
  whale_to_exchange: "bg-amber-500/10 text-amber-300 ring-amber-400/20",
  exchange_netflow: "bg-fuchsia-500/10 text-fuchsia-300 ring-fuchsia-400/20",
};

function TypeBadge({ type }: { type: string }) {
  const cls = TYPE_STYLES[type] ?? "bg-surface-raised text-slate-300 ring-surface-border";
  return (
    <span
      className={
        "inline-flex items-center text-[10px] font-semibold tracking-wider rounded px-1.5 py-0.5 ring-1 " +
        cls
      }
    >
      {type.replace(/_/g, " ")}
    </span>
  );
}

function summarizePayload(ruleType: string, payload: Record<string, unknown>): string {
  const p = payload as Record<string, number | string>;
  switch (ruleType) {
    case "price_above":
      return `${p.symbol} $${Number(p.price).toLocaleString()} ▲ crossed $${Number(p.threshold).toLocaleString()}`;
    case "price_below":
      return `${p.symbol} $${Number(p.price).toLocaleString()} ▼ crossed $${Number(p.threshold).toLocaleString()}`;
    case "price_change_pct": {
      const pct = Number(p.pct_observed);
      return `${p.symbol} ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}% in ${p.window_min}m`;
    }
    case "whale_transfer":
    case "whale_to_exchange": {
      const amt = Number(p.amount);
      const usd = p.usd_value ? formatUsdCompact(Number(p.usd_value)) : "";
      const fromLbl = (p.from_label as string | undefined) ?? "";
      const toLbl = (p.to_label as string | undefined) ?? "";
      const tag = fromLbl || toLbl ? `  ${fromLbl || "?"} → ${toLbl || "?"}` : "";
      return `${amt.toFixed(amt >= 1000 ? 0 : 2)} ${p.asset} ${usd ? `(${usd})` : ""}${tag}`.trim();
    }
    case "exchange_netflow": {
      const d = p.direction;
      const v = Number(p.value_usd);
      return `${p.exchange} ${d} ${formatUsdCompact(v)} over ${p.window_h}h`;
    }
    default:
      return JSON.stringify(payload).slice(0, 120);
  }
}

function DeliveredDots({ delivered }: { delivered: AlertEvent["delivered"] }) {
  const entries = Object.entries(delivered || {});
  if (entries.length === 0) {
    return <span className="text-[10px] text-slate-600">—</span>;
  }
  return (
    <span className="inline-flex gap-1">
      {entries.map(([k, v]) => (
        <span
          key={k}
          title={`${k}: ${v.ok ? "ok" : v.error ?? "fail"}`}
          className={
            "w-1.5 h-1.5 rounded-full inline-block " + (v.ok ? "bg-up" : "bg-down")
          }
        />
      ))}
    </span>
  );
}

type Tab = "events" | "rules";

export default function AlertEventsPanel() {
  const t = useT();
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("events");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<AlertRule | null>(null);

  const events = useQuery({
    queryKey: ["alert-events"],
    queryFn: () => fetchAlertEvents(24, 100),
    refetchInterval: 15_000,
  });
  const rules = useQuery({
    queryKey: ["alert-rules"],
    queryFn: fetchAlertRules,
    refetchInterval: 60_000,
  });

  // Global keyboard shortcut: `n` opens the new-rule modal.
  useEffect(() => {
    const open = () => {
      setEditing(null);
      setTab("rules");
      setModalOpen(true);
    };
    window.addEventListener(NEW_RULE_EVENT, open);
    return () => window.removeEventListener(NEW_RULE_EVENT, open);
  }, []);

  // Toast on new alert fires.
  const seenIds = useRef<Set<number> | null>(null);
  useEffect(() => {
    if (!events.data) return;
    const ids = new Set(events.data.map((e) => e.id));
    if (seenIds.current === null) {
      seenIds.current = ids;
      return;
    }
    const fresh = events.data.filter((e) => !seenIds.current!.has(e.id));
    for (const e of fresh) {
      const ruleType =
        rules.data?.find((r) => r.id === e.rule_id)?.rule_type ?? "alert";
      toast.push({
        title: `🔔 ${e.rule_name ?? `Rule #${e.rule_id}`}`,
        body: summarizePayload(ruleType, e.payload),
        tone:
          ruleType === "price_below" || ruleType === "price_above"
            ? ruleType === "price_above"
              ? "up"
              : "down"
            : "brand",
      });
    }
    seenIds.current = ids;
  }, [events.data, rules.data, toast]);

  const activeRules = rules.data?.filter((r) => r.enabled).length ?? 0;
  const totalRules = rules.data?.length ?? 0;

  const create = useMutation({
    mutationFn: (body: AlertRuleInput) => createAlertRule(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alert-rules"] });
      setModalOpen(false);
      setEditing(null);
      toast.push({ title: t("alerts.toast.created"), tone: "up" });
    },
  });
  const update = useMutation({
    mutationFn: (v: { id: number; body: Partial<AlertRuleInput> }) =>
      patchAlertRule(v.id, v.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alert-rules"] });
      setModalOpen(false);
      setEditing(null);
      toast.push({ title: t("alerts.toast.updated"), tone: "up" });
    },
  });

  async function handleSubmit(input: AlertRuleInput) {
    if (editing) {
      await update.mutateAsync({ id: editing.id, body: input });
    } else {
      await create.mutateAsync(input);
    }
  }

  return (
    <>
      <Card
        title={t("alerts.title")}
        subtitle={
          rules.data
            ? t("alerts.subtitle_with_rules", { active: activeRules, total: totalRules })
            : t("alerts.subtitle_no_rules")
        }
        live={tab === "events"}
        actions={
          <div className="flex flex-col gap-2 @sm:flex-row @sm:items-center @sm:justify-between @sm:gap-0">
            <div className="inline-flex rounded-md border border-surface-border bg-surface-sunken p-0.5">
              {(["events", "rules"] as Tab[]).map((tabVal) => (
                <button
                  key={tabVal}
                  onClick={() => setTab(tabVal)}
                  className={
                    "px-3 py-1 text-xs font-medium tracking-wide rounded transition " +
                    (tab === tabVal
                      ? "bg-surface-raised text-white"
                      : "text-slate-400 hover:text-slate-200")
                  }
                >
                  {tabVal === "events" ? t("alerts.tab.events") : t("alerts.tab.rules")}
                </button>
              ))}
            </div>
            {tab === "rules" && (
              <Button
                variant="primary"
                onClick={() => {
                  setEditing(null);
                  setModalOpen(true);
                }}
              >
                {t("alerts.new_rule")}
              </Button>
            )}
          </div>
        }
        bodyClassName="p-0"
      >
        {tab === "events" && (
          <>
            {events.isLoading && <p className="p-5 text-sm text-slate-500">{t("common.loading")}</p>}
            {events.error && <p className="p-5 text-sm text-down">{t("common.unavailable")}</p>}
            {!events.isLoading &&
              !events.error &&
              events.data &&
              events.data.length === 0 && (
                <p className="p-5 text-sm text-slate-500">
                  {totalRules === 0 ? t("alerts.empty_no_rules") : t("alerts.empty")}
                </p>
              )}

            {events.data && events.data.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-separate border-spacing-0">
                  <thead className="text-[11px] tracking-wider uppercase text-slate-500">
                    <tr>
                      <th className="text-left font-medium px-5 py-3 border-b border-surface-divider">
                        {t("alerts.col.fired")}
                      </th>
                      <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                        {t("alerts.col.rule")}
                      </th>
                      <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                        {t("alerts.col.type")}
                      </th>
                      <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                        {t("alerts.col.detail")}
                      </th>
                      <th className="text-center font-medium px-5 py-3 border-b border-surface-divider">
                        {t("alerts.col.delivery")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.data.map((e, i) => {
                      const ruleType =
                        rules.data?.find((r) => r.id === e.rule_id)?.rule_type ?? "";
                      return (
                        <tr
                          key={e.id}
                          className={
                            "row-hover transition " +
                            (i % 2 === 0 ? "bg-transparent" : "bg-surface-sunken/40")
                          }
                        >
                          <td className="px-5 py-2.5 text-slate-400 whitespace-nowrap border-b border-surface-divider/60">
                            {relativeTime(e.fired_at)}
                          </td>
                          <td className="px-3 py-2.5 text-slate-200 border-b border-surface-divider/60">
                            {e.rule_name ?? `#${e.rule_id}`}
                          </td>
                          <td className="px-3 py-2.5 border-b border-surface-divider/60">
                            <TypeBadge type={ruleType || "unknown"} />
                          </td>
                          <td className="px-3 py-2.5 font-mono text-xs text-slate-300 border-b border-surface-divider/60 line-clamp-1 @sm:line-clamp-none">
                            {summarizePayload(ruleType, e.payload)}
                          </td>
                          <td className="px-5 py-2.5 text-center border-b border-surface-divider/60">
                            <DeliveredDots delivered={e.delivered} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {tab === "rules" && (
          <>
            {rules.isLoading && <p className="p-5 text-sm text-slate-500">{t("common.loading")}</p>}
            {rules.error && <p className="p-5 text-sm text-down">{t("common.unavailable")}</p>}
            {rules.data && (
              <RulesList
                rules={rules.data}
                onEdit={(r) => {
                  setEditing(r);
                  setModalOpen(true);
                }}
              />
            )}
          </>
        )}
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => {
          if (!create.isPending && !update.isPending) {
            setModalOpen(false);
            setEditing(null);
          }
        }}
        title={editing ? t("alerts.modal.edit", { name: editing.name }) : t("alerts.modal.new")}
        wide
      >
        <RuleForm
          initial={editing ?? undefined}
          submitting={create.isPending || update.isPending}
          onSubmit={handleSubmit}
          onCancel={() => {
            setModalOpen(false);
            setEditing(null);
          }}
        />
      </Modal>
    </>
  );
}
