import { useQuery } from "@tanstack/react-query";
import { fetchAlertEvents, fetchAlertRules, type AlertEvent } from "../api";
import { formatUsdCompact, relativeTime } from "../lib/format";
import Card from "./ui/Card";

const TYPE_STYLES: Record<string, string> = {
  price_above: "bg-up/10 text-up ring-up/20",
  price_below: "bg-down/10 text-down ring-down/20",
  price_change_pct: "bg-sky-500/10 text-sky-300 ring-sky-400/20",
  whale_transfer: "bg-brand/15 text-brand-soft ring-brand/20",
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
    case "whale_transfer": {
      const amt = Number(p.amount);
      const usd = p.usd_value ? formatUsdCompact(Number(p.usd_value)) : "";
      return `${amt.toFixed(amt >= 1000 ? 0 : 2)} ${p.asset} ${usd ? `(${usd})` : ""}`.trim();
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

export default function AlertEventsPanel() {
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

  const activeRules = rules.data?.filter((r) => r.enabled).length ?? 0;
  const totalRules = rules.data?.length ?? 0;

  return (
    <Card
      title="Alerts"
      subtitle={
        rules.data
          ? `${activeRules}/${totalRules} rules active · fires in last 24h`
          : "rules · fires in last 24h"
      }
      live
      bodyClassName="p-0"
    >
      {events.isLoading && <p className="p-5 text-sm text-slate-500">loading…</p>}
      {events.error && <p className="p-5 text-sm text-down">unavailable</p>}
      {!events.isLoading && !events.error && events.data && events.data.length === 0 && (
        <p className="p-5 text-sm text-slate-500">
          no alerts in the last 24h — create rules via <code className="text-slate-300">POST /api/alerts/rules</code>
          {totalRules === 0 && " (no rules configured yet)"}
        </p>
      )}

      {events.data && events.data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-separate border-spacing-0">
            <thead className="text-[11px] tracking-wider uppercase text-slate-500">
              <tr>
                <th className="text-left font-medium px-5 py-3 border-b border-surface-divider">
                  Fired
                </th>
                <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                  Rule
                </th>
                <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                  Type
                </th>
                <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
                  Detail
                </th>
                <th className="text-center font-medium px-5 py-3 border-b border-surface-divider">
                  Delivery
                </th>
              </tr>
            </thead>
            <tbody>
              {events.data.map((e, i) => {
                const ruleType =
                  (rules.data?.find((r) => r.id === e.rule_id)?.rule_type as string) ?? "";
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
                    <td className="px-3 py-2.5 font-mono text-xs text-slate-300 border-b border-surface-divider/60">
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
    </Card>
  );
}
