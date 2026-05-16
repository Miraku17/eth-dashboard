"""Alert delivery: Telegram + signed webhook.

Telegram uses the single bot configured via env. Webhooks are HMAC-SHA256 signed
with `WEBHOOK_SIGNING_SECRET`. Both are best-effort: any individual channel
failure is logged and reported back in the `delivered` payload so the event row
still gets written.
"""
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def _fmt_num(v: Any) -> str:
    if isinstance(v, int | float):
        if abs(v) >= 1e9:
            return f"{v / 1e9:.2f}B"
        if abs(v) >= 1e6:
            return f"{v / 1e6:.2f}M"
        if abs(v) >= 1e3:
            return f"{v / 1e3:.1f}K"
        return f"{v:.2f}" if isinstance(v, float) else str(v)
    return str(v)


def format_telegram_message(rule_name: str, rule_type: str, payload: dict) -> str:
    head = f"🔔 *{rule_name}*  `{rule_type}`"
    lines = [head, ""]
    if rule_type in ("price_above", "price_below"):
        arrow = "▲" if rule_type == "price_above" else "▼"
        lines.append(
            f"{arrow} {payload.get('symbol')} = *${_fmt_num(payload.get('price'))}* "
            f"(threshold ${_fmt_num(payload.get('threshold'))})"
        )
    elif rule_type == "price_change_pct":
        lines.append(
            f"{payload.get('symbol')} moved *{payload.get('pct_observed'):+.2f}%* "
            f"in {payload.get('window_min')}m "
            f"(trigger {payload.get('pct_threshold'):+.2f}%)"
        )
        lines.append(
            f"  {_fmt_num(payload.get('price_past'))} → {_fmt_num(payload.get('price_now'))}"
        )
    elif rule_type in ("whale_transfer", "whale_to_exchange"):
        asset = payload.get("asset")
        amount = _fmt_num(payload.get("amount"))
        usd = payload.get("usd_value")
        usd_s = f" (~${_fmt_num(usd)})" if usd else ""
        emoji = "🐋➡️🏦" if rule_type == "whale_to_exchange" else "🐋"
        lines.append(f"{emoji} {amount} {asset}{usd_s}")
        from_part = payload.get("from_label") or f"`{payload.get('from_addr')}`"
        to_part = payload.get("to_label") or f"`{payload.get('to_addr')}`"
        lines.append(f"  from {from_part}")
        lines.append(f"  to   {to_part}")
        tx = payload.get("tx_hash")
        if tx:
            lines.append(f"  [tx](https://etherscan.io/tx/{tx})")
    elif rule_type == "exchange_netflow":
        ex = payload.get("exchange", "ANY")
        direction = payload.get("direction", "net")
        value = payload.get("value_usd", 0)
        threshold = payload.get("threshold_usd", 0)
        lines.append(
            f"🏦 *{ex}* {direction} = *${_fmt_num(value)}* "
            f"over {payload.get('window_h')}h (threshold ${_fmt_num(threshold)})"
        )
        lines.append(
            f"  in ${_fmt_num(payload.get('inflow_usd'))} · "
            f"out ${_fmt_num(payload.get('outflow_usd'))} · "
            f"net ${_fmt_num(payload.get('net_usd'))}"
        )
    elif rule_type == "perp_watch":
        kind = payload.get("event_kind", "?")
        side = payload.get("side", "?")
        if kind in {"open", "increase"}:
            emoji = "🟢" if side == "long" else "🔴"
        else:
            emoji = "⚪"
        score = payload.get("score") or {}
        if score:
            wr_pct = float(score["win_rate"]) * 100
            score_line = (
                f"\n★ {wr_pct:.0f}% win / "
                f"{score['trades']} trades / "
                f"avg {score['avg_hold_secs'] // 60}m"
            )
        else:
            score_line = ""
        wallet_disp = payload.get("label") or (payload.get("wallet", "?")[:10])
        try:
            size = float(payload.get("size_usd", "0"))
            lev = float(payload.get("leverage", "0"))
        except (TypeError, ValueError):
            size, lev = 0.0, 0.0
        lines.append(
            f"{emoji} {kind.upper()}  {payload.get('market','?')}  "
            f"{side.upper()}  ${size:,.0f}  {lev:.1f}x"
        )
        lines.append(f"Wallet: {wallet_disp}{score_line}")
        tx = payload.get("tx_hash", "")
        if tx:
            lines.append(f"Tx: {tx[:12]}…")
    else:
        lines.append(f"```json\n{json.dumps(payload, indent=2)}\n```")
    return "\n".join(lines)


async def send_telegram(
    http: httpx.AsyncClient, text: str, *, token: str, chat_id: str
) -> dict:
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    r = await http.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=10.0,
    )
    r.raise_for_status()
    return {"ok": True}


async def send_webhook(
    http: httpx.AsyncClient, url: str, body: dict, *, secret: str
) -> dict:
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    r = await http.post(
        url,
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Etherscope-Signature": f"sha256={sig}",
        },
        timeout=10.0,
    )
    r.raise_for_status()
    return {"ok": True, "status": r.status_code}


async def dispatch(
    http: httpx.AsyncClient,
    channels: list[dict],
    rule_name: str,
    rule_type: str,
    payload: dict,
) -> dict:
    """Fire-and-forward to each channel; collect per-channel outcome."""
    settings = get_settings()
    results: dict[str, Any] = {}
    text = format_telegram_message(rule_name, rule_type, payload)

    for i, ch in enumerate(channels or []):
        key = f"{ch.get('type')}:{i}"
        try:
            if ch.get("type") == "telegram":
                if not settings.telegram_bot_token or not settings.telegram_chat_id:
                    results[key] = {"ok": False, "error": "telegram not configured"}
                    continue
                results[key] = await send_telegram(
                    http,
                    text,
                    token=settings.telegram_bot_token,
                    chat_id=settings.telegram_chat_id,
                )
            elif ch.get("type") == "webhook":
                url = ch.get("url")
                if not url:
                    results[key] = {"ok": False, "error": "webhook url missing"}
                    continue
                if not settings.webhook_signing_secret:
                    results[key] = {"ok": False, "error": "WEBHOOK_SIGNING_SECRET not set"}
                    continue
                results[key] = await send_webhook(
                    http,
                    url,
                    {"rule": rule_name, "type": rule_type, "payload": payload},
                    secret=settings.webhook_signing_secret,
                )
            else:
                results[key] = {"ok": False, "error": f"unknown channel {ch.get('type')}"}
        except Exception as e:
            log.warning("alert delivery failed channel=%s err=%s", key, e)
            results[key] = {"ok": False, "error": str(e)}
    return results
