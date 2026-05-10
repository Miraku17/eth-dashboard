import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  deleteAlertRule,
  patchAlertRule,
  type AlertRule,
  type AlertRuleInput,
} from "../../api";
import { useT } from "../../i18n/LocaleProvider";
import Button from "../ui/Button";

type Props = {
  rules: AlertRule[];
  onEdit: (rule: AlertRule) => void;
};

function summarizeParams(rule: AlertRule): string {
  const p = rule.params as Record<string, unknown>;
  switch (rule.rule_type) {
    case "price_above":
      return `${p.symbol} ≥ $${Number(p.threshold).toLocaleString()}`;
    case "price_below":
      return `${p.symbol} ≤ $${Number(p.threshold).toLocaleString()}`;
    case "price_change_pct":
      return `${p.symbol} moves ${Number(p.pct) >= 0 ? "+" : ""}${p.pct}% in ${p.window_min}m`;
    case "whale_transfer":
      return `${p.asset} tx ≥ $${Number(p.min_usd).toLocaleString()}`;
    case "whale_to_exchange":
      return `${p.asset} ${p.direction === "any" ? "to/from" : p.direction} CEX ≥ $${Number(p.min_usd).toLocaleString()}`;
    case "exchange_netflow": {
      const d = p.direction === "net" ? "|net|" : p.direction;
      return `${p.exchange} ${d} ≥ $${Number(p.threshold_usd).toLocaleString()} over ${p.window_h}h`;
    }
    default:
      return JSON.stringify(rule.params);
  }
}

export default function RulesList({ rules, onEdit }: Props) {
  const t = useT();
  const qc = useQueryClient();
  const toggle = useMutation({
    mutationFn: (v: { id: number; patch: Partial<AlertRuleInput> }) =>
      patchAlertRule(v.id, v.patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-rules"] }),
  });
  const remove = useMutation({
    mutationFn: (id: number) => deleteAlertRule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-rules"] }),
  });

  if (rules.length === 0) {
    return (
      <p className="p-5 text-sm text-slate-500">
        {t("rules_list.empty", { new_rule: t("alerts.new_rule") })}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-separate border-spacing-0">
        <thead className="text-[11px] tracking-wider uppercase text-slate-500">
          <tr>
            <th className="text-left font-medium px-5 py-3 border-b border-surface-divider">
              {t("rules_list.col.name")}
            </th>
            <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
              {t("rules_list.col.type")}
            </th>
            <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
              {t("rules_list.col.condition")}
            </th>
            <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
              {t("rules_list.col.channels")}
            </th>
            <th className="text-left font-medium px-3 py-3 border-b border-surface-divider">
              {t("rules_list.col.cooldown")}
            </th>
            <th className="text-center font-medium px-3 py-3 border-b border-surface-divider">
              {t("rules_list.col.enabled")}
            </th>
            <th className="text-right font-medium px-5 py-3 border-b border-surface-divider">
              {t("rules_list.col.actions")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rules.map((r, i) => (
            <tr
              key={r.id}
              className={
                "transition " + (i % 2 === 0 ? "bg-transparent" : "bg-surface-sunken/40")
              }
            >
              <td className="px-5 py-2.5 text-slate-200 border-b border-surface-divider/60">
                {r.name}
              </td>
              <td className="px-3 py-2.5 border-b border-surface-divider/60">
                <span className="text-[11px] font-mono text-slate-400">{r.rule_type}</span>
              </td>
              <td className="px-3 py-2.5 font-mono text-xs text-slate-300 border-b border-surface-divider/60">
                {summarizeParams(r)}
              </td>
              <td className="px-3 py-2.5 text-xs text-slate-400 border-b border-surface-divider/60">
                {r.channels.length === 0 ? (
                  <span className="text-slate-600">—</span>
                ) : (
                  r.channels.map((c) => c.type).join(", ")
                )}
              </td>
              <td className="px-3 py-2.5 text-xs font-mono text-slate-400 border-b border-surface-divider/60">
                {r.cooldown_min != null ? `${r.cooldown_min}m` : t("rules_list.cooldown_default")}
              </td>
              <td className="px-3 py-2.5 text-center border-b border-surface-divider/60">
                <button
                  onClick={() =>
                    toggle.mutate({ id: r.id, patch: { enabled: !r.enabled } })
                  }
                  aria-label={r.enabled ? t("rules_list.aria.disable") : t("rules_list.aria.enable")}
                  className={
                    "relative inline-flex items-center h-5 w-9 rounded-full transition " +
                    (r.enabled ? "bg-up/70" : "bg-surface-raised")
                  }
                >
                  <span
                    className={
                      "inline-block w-3.5 h-3.5 rounded-full bg-white transform transition " +
                      (r.enabled ? "translate-x-5" : "translate-x-1")
                    }
                  />
                </button>
              </td>
              <td className="px-5 py-2.5 text-right border-b border-surface-divider/60">
                <div className="inline-flex gap-2 justify-end">
                  <Button variant="ghost" onClick={() => onEdit(r)}>
                    {t("common.edit")}
                  </Button>
                  <Button
                    variant="danger"
                    onClick={() => {
                      if (confirm(t("rules_list.confirm_delete", { name: r.name }))) remove.mutate(r.id);
                    }}
                    disabled={remove.isPending}
                  >
                    {t("common.delete")}
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
