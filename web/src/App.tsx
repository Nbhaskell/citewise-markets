import { Link, NavLink, Route, Routes } from "react-router-dom";
import { CopilotPage } from "./pages/CopilotPage";
import { Dashboard } from "./pages/Dashboard";
import { StockPage } from "./pages/StockPage";

function NotFound() {
  return (
    <section className="card">
      <h2>Page not found</h2>
      <p>
        <Link to="/">Back to the dashboard</Link>
      </p>
    </section>
  );
}

export function App() {
  return (
    <div className="app">
      <header className="app-header">
        <Link to="/" className="brand">
          stockMarket
        </Link>
        <nav className="main-nav" aria-label="Main">
          <NavLink to="/" end>
            Dashboard
          </NavLink>
          <NavLink to="/copilot">Copilot</NavLink>
        </nav>
        <span className="muted small">Research from public filings, prices, and headlines. Not financial advice.</span>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/stocks/:symbol" element={<StockPage />} />
          <Route path="/copilot" element={<CopilotPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  );
}
