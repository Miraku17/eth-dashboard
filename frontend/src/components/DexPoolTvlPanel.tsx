import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDexPoolTvlLatest, type DexPoolTvlPoint } from "../api";
import { formatUsdCompact } from "../lib/format";
import Card from "./ui/Card";
import DataAge from "./ui/DataAge";
import { SimpleSelect } from "./ui/Select";

const TOP_N_DISPLAY = 20;

type DexFilter = "ALL" | "uniswap-v3" | "uniswap-v2" | "curve-dex" | "balancer-v2";

const DEX_LABELS: Record<DexFilter, string> = {
  ALL: "All DEXes",
  "uniswap-v3": "Uniswap v3",
  "uniswap-v2": "Uniswap v2",
  "curve-dex": "Curve",
  "balancer-v2": "Balancer v2",
};

const DEX_OPTIONS: { value: DexFilter; label: string }[] = [
  { value: "ALL", label: "All DEXes" },
  { value: "uniswap-v3", label: "Uniswap v3" },
  { value: "uniswap-v2", label: "Uniswap v2" },
  { value: "curve-dex", label: "Curve" },
  { value: "balancer-v2", label: "Balancer v2" },
];

export default function DexPoolTvlPanel() {
  const [filter, setFilter] = useState<DexFilter>("ALL");

  const { data, isLoading, error } = useQuery({
    queryKey: ["dex-pool-tvl-latest"],
    queryFn: fetchDexPoolTvlLatest,
    refetchInterval: 5 * 60_000,
  });

  const filtered = useMemo<DexPoolTvlPoint[]>(() => {
    const pools = data?.pools ?? [];
    const view = filter === "ALL" ? pools : pools.filter((p) => p.dex === filter);
    return view.slice(0, TOP_N_DISPLAY);
  }, [data, filter]);

  const max = Math.max(1, ...filtered.map((p) => p.tvl_usd));
  const totalView = filtered.reduce((s, p) => s + p.tvl_usd, 0);

  return (
    <Card
      title="DEX pool TVL"
      subtitle={`Ethereum mainnet · top ${TOP_N_DISPLAY} pools by TVL · DefiLlama`}
      actions={
        <SimpleSelect
          value={filter}
          onChange={setFilter}
          options={DEX_OPTIONS}
          ariaLabel="Filter by DEX"
        />
      }
    >
      {isLoading && <p className="text-sm text-slate-500">loading…</p>}
      {error && <p className="text-sm text-down">unavailable</p>}
      {!isLoading && !error && filtered.length === 0 && (
        <p className="text-sm text-slate-500">
          no data yet — first hourly sync pending
        </p>
      )}
      {filtered.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-slate-500">{filtered.length} pools shown</span>
            <span className="font-mono tabular-nums text-slate-300">
              {formatUsdCompact(totalView)} combined
            </span>
          </div>
          <DataAge ts={data?.ts_bucket ?? null} />
          <ul className="space-y-2">
            {filtered.map((p) => {
              const barPct = (p.tvl_usd / max) * 100;
              return (
                <li key={p.pool_id} className="text-sm">
                  <div className="flex justify-between mb-1 gap-2 min-w-0">
                    <span className="truncate min-w-0">
                      <span className="text-slate-500 text-[11px] mr-1.5">
                        {DEX_LABELS[p.dex as DexFilter] ?? p.dex}
                      </span>
                      <span className="text-slate-200 font-medium">{p.symbol}</span>
                    </span>
                    <span className="font-mono tabular-nums text-slate-200 shrink-0">
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
