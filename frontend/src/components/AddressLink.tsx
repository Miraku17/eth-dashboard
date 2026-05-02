import { useState } from "react";
import { Check, Copy } from "lucide-react";

import { useWalletDrawer } from "../state/walletDrawer";

type Props = {
  address: string;
  className?: string;
  /** Optional override for the visible text (e.g. an existing label). */
  label?: string | null;
};

function truncate(addr: string): string {
  if (addr.length < 10) return addr;
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

export default function AddressLink({ address, className, label }: Props) {
  const show = useWalletDrawer((s) => s.show);
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(address).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    });
  };

  return (
    <span className="group/addr inline-flex items-center gap-1">
      <button
        type="button"
        onClick={() => show(address)}
        className={
          "font-mono tabular-nums underline decoration-dotted underline-offset-2 " +
          "hover:text-brand-soft transition " +
          (className ?? "")
        }
        title={address}
      >
        {label ?? truncate(address)}
      </button>
      <button
        type="button"
        onClick={handleCopy}
        className={
          "opacity-0 group-hover/addr:opacity-60 hover:!opacity-100 transition " +
          "text-slate-400 hover:text-brand-soft"
        }
        title={copied ? "Copied!" : "Copy address"}
        aria-label={copied ? "Copied!" : "Copy address"}
      >
        {copied ? <Check size={11} /> : <Copy size={11} />}
      </button>
    </span>
  );
}
