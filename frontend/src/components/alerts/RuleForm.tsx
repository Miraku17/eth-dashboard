import { useState } from "react";
import type { AlertRuleInput, AlertRule } from "../../api";
import Button from "../ui/Button";

type Props = {
  initial?: AlertRule;
  onSubmit: (input: AlertRuleInput) => Promise<void> | void;
  onCancel: () => void;
  submitting?: boolean;
};

type RuleType =
  | "price_above"
  | "price_below"
  | "price_change_pct"
  | "whale_transfer"
  | "whale_to_exchange"
  | "exchange_netflow"
  | "wallet_score_move";

const RULE_TYPE_LABELS: Record<RuleType, string> = {
  price_above: "Price above threshold",
  price_below: "Price below threshold",
  price_change_pct: "Price % change in window",
  whale_transfer: "Whale transfer (any)",
  whale_to_exchange: "Whale transfer to/from exchange",
  exchange_netflow: "Exchange netflow over window",
  wallet_score_move: "★ Smart-money wallet move",
};

const DEFAULTS: Record<RuleType, Record<string, unknown>> = {
  price_above: { symbol: "ETHUSDT", threshold: 4000 },
  price_below: { symbol: "ETHUSDT", threshold: 3000 },
  price_change_pct: { symbol: "ETHUSDT", window_min: 60, pct: 3 },
  whale_transfer: { asset: "ANY", min_usd: 5_000_000 },
  whale_to_exchange: { asset: "ANY", min_usd: 1_000_000, direction: "any" },
  exchange_netflow: {
    exchange: "ANY",
    window_h: 24,
    threshold_usd: 50_000_000,
    direction: "net",
  },
  wallet_score_move: {
    asset: "ANY",
    min_usd: 1_000_000,
    min_score: 100_000,
    direction: "any",
  },
};

const WHALE_ASSETS = ["ANY", "ETH", "USDT", "USDC", "DAI"] as const;
const EXCHANGES = ["ANY", "Binance", "Coinbase", "Kraken", "OKX", "Bitfinex", "Bybit"] as const;

function label(text: string) {
  return (
    <span className="text-[11px] tracking-wider uppercase text-slate-500 font-medium block mb-1">
      {text}
    </span>
  );
}

function field(cls = "") {
  return (
    "w-full rounded-md bg-surface-sunken border border-surface-border px-3 py-2 text-sm text-slate-100 " +
    "focus:outline-none focus:border-brand/60 focus:ring-1 focus:ring-brand/40 " +
    cls
  );
}

export default function RuleForm({ initial, onSubmit, onCancel, submitting }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [ruleType, setRuleType] = useState<RuleType>(
    (initial?.rule_type as RuleType | undefined) ?? "price_above",
  );
  const [params, setParams] = useState<Record<string, unknown>>(
    initial ? { ...initial.params } : { ...DEFAULTS["price_above"] },
  );
  const [cooldown, setCooldown] = useState<string>(
    initial?.cooldown_min != null ? String(initial.cooldown_min) : "",
  );
  const [channels, setChannels] = useState<AlertRule["channels"]>(
    initial?.channels ?? [{ type: "telegram" }],
  );
  const [error, setError] = useState<string | null>(null);

  function changeType(t: RuleType) {
    setRuleType(t);
    setParams({ ...DEFAULTS[t] });
  }

  function setParam(k: string, v: unknown) {
    setParams((p) => ({ ...p, [k]: v }));
  }

  function toggleChannel(type: "telegram" | "webhook") {
    setChannels((curr) => {
      const has = curr.find((c) => c.type === type);
      if (has) return curr.filter((c) => c.type !== type);
      return [...curr, type === "webhook" ? { type, url: "" } : { type }];
    });
  }

  function setWebhookUrl(url: string) {
    setChannels((curr) => curr.map((c) => (c.type === "webhook" ? { ...c, url } : c)));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("name is required");
      return;
    }
    const wh = channels.find((c) => c.type === "webhook");
    if (wh && !wh.url) {
      setError("webhook URL is required when webhook channel is enabled");
      return;
    }
    const cd = cooldown.trim() === "" ? undefined : Number(cooldown);
    if (cd !== undefined && (isNaN(cd) || cd < 0)) {
      setError("cooldown must be a non-negative number");
      return;
    }
    try {
      await onSubmit({
        name: name.trim(),
        params: { rule_type: ruleType, ...params },
        channels,
        cooldown_min: cd ?? null,
        enabled: initial?.enabled ?? true,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to save");
    }
  }

  const telegramOn = channels.some((c) => c.type === "telegram");
  const webhookCh = channels.find((c) => c.type === "webhook");

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        {label("Name")}
        <input
          className={field()}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. ETH above $4k"
          required
          maxLength={128}
        />
      </div>

      <div>
        {label("Rule type")}
        <select
          className={field()}
          value={ruleType}
          onChange={(e) => changeType(e.target.value as RuleType)}
          disabled={!!initial}
        >
          {(Object.keys(RULE_TYPE_LABELS) as RuleType[]).map((t) => (
            <option key={t} value={t}>
              {RULE_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
        {!!initial && (
          <p className="text-[11px] text-slate-500 mt-1">
            rule type can't be changed after creation
          </p>
        )}
      </div>

      {/* Per-type param fields */}
      <div className="grid grid-cols-2 gap-3">
        {(ruleType === "price_above" || ruleType === "price_below") && (
          <>
            <div>
              {label("Symbol")}
              <input
                className={field()}
                value={String(params.symbol ?? "ETHUSDT")}
                onChange={(e) => setParam("symbol", e.target.value)}
              />
            </div>
            <div>
              {label("Threshold (USD)")}
              <input
                type="number"
                step="any"
                className={field()}
                value={String(params.threshold ?? "")}
                onChange={(e) => setParam("threshold", Number(e.target.value))}
                required
              />
            </div>
          </>
        )}

        {ruleType === "price_change_pct" && (
          <>
            <div>
              {label("Symbol")}
              <input
                className={field()}
                value={String(params.symbol ?? "ETHUSDT")}
                onChange={(e) => setParam("symbol", e.target.value)}
              />
            </div>
            <div>
              {label("Window (minutes)")}
              <input
                type="number"
                className={field()}
                value={String(params.window_min ?? 60)}
                min={5}
                max={24 * 60}
                onChange={(e) => setParam("window_min", Number(e.target.value))}
              />
            </div>
            <div className="col-span-2">
              {label("Trigger % (negative = down move)")}
              <input
                type="number"
                step="any"
                className={field()}
                value={String(params.pct ?? 3)}
                onChange={(e) => setParam("pct", Number(e.target.value))}
              />
            </div>
          </>
        )}

        {(ruleType === "whale_transfer" || ruleType === "whale_to_exchange") && (
          <>
            <div>
              {label("Asset")}
              <select
                className={field()}
                value={String(params.asset ?? "ANY")}
                onChange={(e) => setParam("asset", e.target.value)}
              >
                {WHALE_ASSETS.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </div>
            <div>
              {label("Minimum USD")}
              <input
                type="number"
                step="any"
                className={field()}
                value={String(params.min_usd ?? 1_000_000)}
                onChange={(e) => setParam("min_usd", Number(e.target.value))}
                required
              />
            </div>
            {ruleType === "whale_to_exchange" && (
              <div className="col-span-2">
                {label("Direction")}
                <select
                  className={field()}
                  value={String(params.direction ?? "any")}
                  onChange={(e) => setParam("direction", e.target.value)}
                >
                  <option value="any">any (either side labeled)</option>
                  <option value="to">to exchange</option>
                  <option value="from">from exchange</option>
                </select>
              </div>
            )}
          </>
        )}

        {ruleType === "exchange_netflow" && (
          <>
            <div>
              {label("Exchange")}
              <select
                className={field()}
                value={String(params.exchange ?? "ANY")}
                onChange={(e) => setParam("exchange", e.target.value)}
              >
                {EXCHANGES.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </select>
            </div>
            <div>
              {label("Window (hours)")}
              <input
                type="number"
                className={field()}
                value={String(params.window_h ?? 24)}
                min={1}
                max={24 * 30}
                onChange={(e) => setParam("window_h", Number(e.target.value))}
              />
            </div>
            <div>
              {label("Threshold (USD)")}
              <input
                type="number"
                step="any"
                className={field()}
                value={String(params.threshold_usd ?? 50_000_000)}
                onChange={(e) => setParam("threshold_usd", Number(e.target.value))}
              />
            </div>
            <div>
              {label("Direction")}
              <select
                className={field()}
                value={String(params.direction ?? "net")}
                onChange={(e) => setParam("direction", e.target.value)}
              >
                <option value="net">|net|</option>
                <option value="in">inflow</option>
                <option value="out">outflow</option>
              </select>
            </div>
          </>
        )}

        {ruleType === "wallet_score_move" && (
          <>
            <div>
              {label("Asset")}
              <select
                className={field()}
                value={String(params.asset ?? "ANY")}
                onChange={(e) => setParam("asset", e.target.value)}
              >
                {WHALE_ASSETS.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </div>
            <div>
              {label("Minimum USD")}
              <input
                type="number"
                step="any"
                className={field()}
                value={String(params.min_usd ?? 1_000_000)}
                onChange={(e) => setParam("min_usd", Number(e.target.value))}
                required
              />
            </div>
            <div>
              {label("Minimum smart score (USD)")}
              <input
                type="number"
                step="any"
                className={field()}
                value={String(params.min_score ?? 100_000)}
                onChange={(e) => setParam("min_score", Number(e.target.value))}
                required
              />
            </div>
            <div>
              {label("Direction")}
              <select
                className={field()}
                value={String(params.direction ?? "any")}
                onChange={(e) => setParam("direction", e.target.value)}
              >
                <option value="any">any (smart on either side)</option>
                <option value="from">smart sender (smart →)</option>
                <option value="to">smart receiver (→ smart)</option>
              </select>
            </div>
          </>
        )}
      </div>

      <div>
        {label("Cooldown (minutes, optional)")}
        <input
          type="number"
          className={field()}
          value={cooldown}
          min={0}
          placeholder="default: 15 (price + netflow only)"
          onChange={(e) => setCooldown(e.target.value)}
        />
      </div>

      <div>
        {label("Channels")}
        <div className="flex gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => toggleChannel("telegram")}
            className={
              "px-3 py-1.5 rounded-md text-sm font-medium border transition " +
              (telegramOn
                ? "bg-brand/15 text-brand-soft border-brand/40"
                : "bg-surface-sunken text-slate-400 border-surface-border hover:text-white")
            }
          >
            Telegram
          </button>
          <button
            type="button"
            onClick={() => toggleChannel("webhook")}
            className={
              "px-3 py-1.5 rounded-md text-sm font-medium border transition " +
              (webhookCh
                ? "bg-brand/15 text-brand-soft border-brand/40"
                : "bg-surface-sunken text-slate-400 border-surface-border hover:text-white")
            }
          >
            Webhook
          </button>
        </div>
        {webhookCh && (
          <input
            className={field("mt-2")}
            placeholder="https://your.service/hook"
            value={webhookCh.url ?? ""}
            onChange={(e) => setWebhookUrl(e.target.value)}
            type="url"
          />
        )}
        {channels.length === 0 && (
          <p className="text-[11px] text-slate-500 mt-1">
            No channels — events will still be logged in the dashboard.
          </p>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-down/30 bg-down/10 text-down text-sm px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <Button variant="ghost" type="button" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button variant="primary" type="submit" disabled={submitting}>
          {submitting ? "Saving…" : initial ? "Save changes" : "Create rule"}
        </Button>
      </div>
    </form>
  );
}
