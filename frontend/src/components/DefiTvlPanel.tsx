import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDefiTvlLatest, type DefiTvlProtocolSnapshot } from "../api";
import { formatUsdCompact } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import Card from "./ui/Card";
import DataAge from "./ui/DataAge";
import { SimpleSelect } from "./ui/Select";

const TOP_N_ASSETS = 12;

export default function DefiTvlPanel() {
  const t = useT();
  const { data, isLoading, error } = useQuery({
    queryKey: ["defi-tvl-latest"],
    queryFn: fetchDefiTvlLatest,
    refetchInterval: 5 * 60_000,
  });

  const protocols = data?.protocols ?? [];
  const [selectedSlug, setSelectedSlug] = useState<string>("");

  // First-render and refetch sync: pick the first (highest-TVL) protocol if
  // the user hasn't picked one yet, or if their pick has dropped out of the
  // current snapshot.
  const effectiveSlug = useMemo(() => {
    if (selectedSlug && protocols.some((p) => p.protocol === selectedSlug)) {
      return selectedSlug;
    }
    return protocols[0]?.protocol ?? "";
  }, [protocols, selectedSlug]);

  const current: DefiTvlProtocolSnapshot | undefined = protocols.find(
    (p) => p.protocol === effectiveSlug,
  );

  const options = protocols.map((p) => ({ value: p.protocol, label: p.display_name }));

  return (
    <Card
      title={t("defi-tvl.title")}
      subtitle={t("defi-tvl.subtitle")}
      actions={
        options.length > 0 && (
          <SimpleSelect
            value={effectiveSlug}
            onChange={setSelectedSlug}
            options={options}
            ariaLabel={t("defi-tvl.aria.select_protocol")}
          />
        )
      }
    >
      {isLoading && <p className="text-sm text-slate-500">{t("common.loading")}</p>}
      {error && <p className="text-sm text-down">{t("common.unavailable")}</p>}
      {!isLoading && !error && protocols.length === 0 && (
        <p className="text-sm text-slate-500">
          {t("defi-tvl.empty")}
        </p>
      )}
      {current && (
        <div className="space-y-3">
          <DataAge ts={data?.ts_bucket ?? null} />
          <ProtocolBreakdown snapshot={current} t={t} />
        </div>
      )}
    </Card>
  );
}

function ProtocolBreakdown({ snapshot, t }: { snapshot: DefiTvlProtocolSnapshot; t: ReturnType<typeof useT> }) {
  const top = snapshot.assets.slice(0, TOP_N_ASSETS);
  const restCount = Math.max(0, snapshot.assets.length - TOP_N_ASSETS);
  const restUsd = snapshot.assets
    .slice(TOP_N_ASSETS)
    .reduce((s, a) => s + a.tvl_usd, 0);
  const max = Math.max(1, ...top.map((a) => a.tvl_usd));

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-slate-300">{snapshot.display_name}</span>
        <span className="font-mono tabular-nums text-base text-slate-100">
          {t("defi-tvl.locked", { value: formatUsdCompact(snapshot.total_usd) })}
        </span>
      </div>

      <ul className="space-y-2">
        {top.map((a) => {
          const pct = (a.tvl_usd / snapshot.total_usd) * 100;
          const barPct = (a.tvl_usd / max) * 100;
          return (
            <li key={a.asset} className="text-sm">
              <div className="flex justify-between mb-1">
                <span className="text-slate-300 font-medium">{a.asset}</span>
                <span className="font-mono tabular-nums text-slate-200 @xs:hidden">
                  {formatUsdCompact(a.tvl_usd)}{" "}
                  <span className="text-slate-500">{pct.toFixed(1)}%</span>
                </span>
                <span className="font-mono tabular-nums text-slate-200 hidden @xs:inline">
                  {formatUsdCompact(a.tvl_usd)}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-surface-raised overflow-hidden">
                <div
                  className="h-full bg-brand/70 rounded-full"
                  style={{ width: `${barPct}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>

      {restCount > 0 && (
        <div className="text-[11px] text-slate-500 font-mono tabular-nums @xs:hidden">
          {t("defi-tvl.more_assets", { count: String(restCount), value: formatUsdCompact(restUsd) })}
        </div>
      )}
    </div>
  );
}
