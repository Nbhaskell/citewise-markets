import { Link, Route, Routes } from "react-router-dom";
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
        <span className="muted small">Research from public filings. Not financial advice.</span>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/stocks/:symbol" element={<StockPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  );
}
