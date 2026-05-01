import { Outlet } from "react-router-dom";

import Topbar from "./Topbar";
import { useGlobalShortcuts } from "../hooks/useGlobalShortcuts";

export default function DashboardShell() {
  useGlobalShortcuts();
  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="mx-auto max-w-[1600px] px-4 sm:px-6 py-6 space-y-6">
        <Outlet />
        <footer className="pt-4 pb-6 text-center text-[11px] text-slate-600">
          Data: Binance · Dune Analytics · Alchemy · Etherscan · CoinGecko
        </footer>
      </main>
    </div>
  );
}
