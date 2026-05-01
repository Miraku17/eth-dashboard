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
  return (
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
  );
}
