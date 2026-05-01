import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchCluster,
  refreshCluster,
  type ClusterResult,
  type LinkedWallet,
} from "../api";
import { useWalletDrawer } from "../state/walletDrawer";

function ConfidenceChip({ confidence }: { confidence: LinkedWallet["confidence"] }) {
  const cls =
    confidence === "strong"
      ? "bg-up/15 text-up ring-up/30"
      : "bg-amber-400/15 text-amber-300 ring-amber-400/30";
  return (
    <span className={`px-1.5 py-0.5 text-[10px] uppercase tracking-wider rounded ring-1 ${cls}`}>
      {confidence}
    </span>
  );
}

function ReasonLine({ reasons }: { reasons: string[] }) {
  return (
    <div className="text-[11px] text-slate-500 font-mono truncate">
      {reasons.map((r, i) => {
        const [kind, ...rest] = r.split(":");
        const human =
          kind === "shared_cex_deposit"
            ? `shared CEX deposit (${rest[0]})`
            : kind === "shared_gas_funder"
              ? `shared gas funder ${rest[0].slice(0, 6)}…`
              : r;
        return (
          <span key={i}>
            {human}
            {i < reasons.length - 1 ? " · " : ""}
          </span>
        );
      })}
    </div>
  );
}

function Body({ data }: { data: ClusterResult }) {
  return (
    <div className="space-y-5">
      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500">Address</div>
        <div className="font-mono text-sm break-all">{data.address}</div>
        {data.labels.length > 0 && (
          <div className="mt-1 flex gap-1 flex-wrap">
            {data.labels.map((l) => (
              <span key={l} className="px-1.5 py-0.5 text-[10px] rounded bg-brand/20 text-brand-soft">
                {l}
              </span>
            ))}
          </div>
        )}
      </div>

      {data.stale && (
        <div className="rounded ring-1 ring-amber-400/30 bg-amber-400/10 px-3 py-2 text-[12px] text-amber-200">
          Showing stale result — Etherscan unavailable.
          Computed {new Date(data.computed_at).toLocaleString()}.
        </div>
      )}

      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1.5">
          Linked wallets ({data.linked_wallets.length})
        </div>
        {data.linked_wallets.length === 0 ? (
          <div className="text-sm text-slate-500">
            No linked wallets found. Common for fresh wallets and wallets funded
            only via public services.
          </div>
        ) : (
          <ul className="divide-y divide-surface-divider">
            {data.linked_wallets.map((lw) => (
              <li key={lw.address} className="py-2 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-sm truncate">
                    {lw.label ?? lw.address}
                  </div>
                  <ReasonLine reasons={lw.reasons} />
                </div>
                <ConfidenceChip confidence={lw.confidence} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1.5">Stats</div>
        <dl className="grid grid-cols-2 gap-y-1 text-[12px]">
          <dt className="text-slate-500">tx count (sample)</dt>
          <dd className="font-mono tabular-nums">{data.stats.tx_count}</dd>
          <dt className="text-slate-500">first seen</dt>
          <dd className="font-mono tabular-nums">
            {data.stats.first_seen ? new Date(data.stats.first_seen).toLocaleDateString() : "—"}
          </dd>
          <dt className="text-slate-500">last seen</dt>
          <dd className="font-mono tabular-nums">
            {data.stats.last_seen ? new Date(data.stats.last_seen).toLocaleDateString() : "—"}
          </dd>
        </dl>
      </div>
    </div>
  );
}

export default function WalletDrawer() {
  const open = useWalletDrawer((s) => s.open);
  const address = useWalletDrawer((s) => s.address);
  const close = useWalletDrawer((s) => s.close);
  const qc = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["cluster", address],
    queryFn: () => fetchCluster(address!),
    enabled: open && !!address,
    refetchOnWindowFocus: false,
  });

  if (!open || !address) return null;

  async function handleRefresh() {
    if (!address) return;
    await refreshCluster(address);
    qc.invalidateQueries({ queryKey: ["cluster", address] });
    refetch();
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end" onClick={close}>
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-[1px]"
        aria-hidden
      />
      <aside
        className="relative z-50 w-full max-w-md h-full bg-surface-base ring-1 ring-surface-border shadow-2xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-surface-divider">
          <div className="font-medium text-slate-200">Wallet</div>
          <div className="flex items-center gap-2">
            <a
              href={`https://etherscan.io/address/${address}`}
              target="_blank"
              rel="noreferrer"
              className="text-[12px] text-slate-400 hover:text-brand-soft underline decoration-dotted"
            >
              Etherscan ↗
            </a>
            <button
              type="button"
              onClick={handleRefresh}
              className="text-[12px] text-slate-400 hover:text-brand-soft"
            >
              ↻ Refresh
            </button>
            <button
              type="button"
              onClick={close}
              className="text-slate-400 hover:text-slate-100 text-lg leading-none px-1"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>

        <div className="p-5">
          {isLoading && <div className="text-sm text-slate-500">loading…</div>}
          {error && <div className="text-sm text-down">unavailable — try again</div>}
          {data && <Body data={data} />}
        </div>
      </aside>
    </div>
  );
}
