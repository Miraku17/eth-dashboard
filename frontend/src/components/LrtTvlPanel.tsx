import { useQuery } from "@tanstack/react-query";
import { fetchLrtTvlLatest, fetchStakingYields } from "../api";
import { formatUsdCompact } from "../lib/format";
import { useT } from "../i18n/LocaleProvider";
import Card from "./ui/Card";
import DataAge from "./ui/DataAge";

export default function LrtTvlPanel() {
  const t = useT();
  const { data, isLoading, error } = useQuery({
    queryKey: ["lrt-tvl-latest"],
    queryFn: fetchLrtTvlLatest,
    refetchInterval: 5 * 60_000,
  });

  const { data: yields } = useQuery({
    queryKey: ["staking-yields"],
    queryFn: fetchStakingYields,
    refetchInterval: 30 * 60_000,
  });

  const protocols = data?.protocols ?? [];
  const totalUsd = data?.total_usd ?? 0;
  const max = Math.max(1, ...protocols.map((p) => p.tvl_usd));

  return (
    <Card
      title={t("lrt-tvl.title")}
      subtitle={t("lrt-tvl.subtitle")}
    >
      {isLoading && <p className="text-sm text-slate-500">{t("common.loading")}</p>}
      {error && <p className="text-sm text-down">{t("common.unavailable")}</p>}
      {!isLoading && !error && protocols.length === 0 && (
        <p className="text-sm text-slate-500">
          {t("lrt-tvl.empty")}
        </p>
      )}
      {protocols.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-baseline justify-between">
            <DataAge ts={data?.ts_bucket ?? null} />
            <span className="font-mono tabular-nums text-base text-slate-100">
              {t("lrt-tvl.total", { value: formatUsdCompact(totalUsd) })}
            </span>
          </div>

          <ul className="space-y-2">
            {protocols.map((p) => {
              const pct = totalUsd > 0 ? (p.tvl_usd / totalUsd) * 100 : 0;
              const barPct = (p.tvl_usd / max) * 100;
              const apy = yields?.lrt[p.protocol] ?? null;
              return (
                <li key={p.protocol} className="text-sm">
                  <div className="flex justify-between mb-1">
                    <span className="text-slate-300 font-medium">
                      {p.display_name}
                      {p.token && (
                        <span className="text-slate-500 font-mono ml-1.5 text-[11px]">
                          {p.token}
                        </span>
                      )}
                    </span>
                    <span className="font-mono tabular-nums text-slate-200 @xs:hidden flex items-center gap-2">
                      <span className="text-up text-[11px]">
                        {apy != null ? `${apy.toFixed(2)}%` : "—"}
                      </span>
                      <span>{formatUsdCompact(p.tvl_usd)}</span>
                      <span className="text-slate-500">{pct.toFixed(1)}%</span>
                    </span>
                    <span className="font-mono tabular-nums text-slate-200 hidden @xs:inline">
                      {formatUsdCompact(p.tvl_usd)}
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
        </div>
      )}
    </Card>
  );
}
