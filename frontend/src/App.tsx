import { BrowserRouter, Route, Routes } from "react-router-dom";

import AuthGate from "./components/AuthGate";
import DashboardShell from "./components/DashboardShell";
import WalletDrawer from "./components/WalletDrawer";
import OverviewPage from "./routes/OverviewPage";

export default function App() {
  return (
    <AuthGate>
      <BrowserRouter>
        <Routes>
          <Route element={<DashboardShell />}>
            <Route index element={<OverviewPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <WalletDrawer />
    </AuthGate>
  );
}
