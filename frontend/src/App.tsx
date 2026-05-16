import { BrowserRouter, Route, Routes } from "react-router-dom";

import AuthGate from "./components/AuthGate";
import DashboardShell from "./components/DashboardShell";
import LocaleToggle from "./components/LocaleToggle";
import WalletDrawer from "./components/WalletDrawer";
import { LocaleProvider } from "./i18n/LocaleProvider";
import CopyTradingPage from "./routes/CopyTradingPage";
import MarketsPage from "./routes/MarketsPage";
import MempoolPage from "./routes/MempoolPage";
import OnchainPage from "./routes/OnchainPage";
import OverviewPage from "./routes/OverviewPage";

export default function App() {
  return (
    <LocaleProvider>
      <AuthGate>
        <BrowserRouter>
          <Routes>
            <Route element={<DashboardShell />}>
              <Route index element={<OverviewPage />} />
              <Route path="markets" element={<MarketsPage />} />
              <Route path="copy-trading" element={<CopyTradingPage />} />
              <Route path="onchain" element={<OnchainPage />} />
              <Route path="mempool" element={<MempoolPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
        <WalletDrawer />
      </AuthGate>
      <LocaleToggle />
    </LocaleProvider>
  );
}
