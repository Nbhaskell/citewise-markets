import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { RemoveOut } from "../api/types";
import { CopilotBox } from "../components/CopilotBox";
import { FilingsList } from "../components/FilingsList";
import { Fundamentals } from "../components/Fundamentals";
import { KeyStats } from "../components/KeyStats";
import { NewsPanel } from "../components/NewsPanel";
import { PriceHistory } from "../components/PriceHistory";
import { RemoveCompany } from "../components/RemoveCompany";
import { useApi } from "../hooks/useApi";
import { directionOf, formatChangePct, formatPrice } from "../lib/format";

const TICKER = /^[A-Za-z][A-Za-z0-9.-]{0,9}$/;

const EXAMPLES = [
  "What are the biggest risks?",
  "How many employees are there?",
  "How did revenue change in the latest annual report?",
  "What do the filings say about competition?",
];

function Missing({ title, hint }: { title: string; hint: string }) {
  return (
    <section className="card">
      <h1 className="page-title">{title}</h1>
      <p className="muted">{hint}</p>
      <p>
        <Link to="/">Back to the dashboard</Link>
      </p>
    </section>
  );
}

export function StockPage() {
  const { symbol = "" } = useParams();
  if (!TICKER.test(symbol)) {
    return <Missing title="That doesn't look like a ticker" hint="Tickers are letters like AAPL or BRK.B." />;
  }
  return <StockDetailView symbol={symbol.toUpperCase()} />;
}

function StockDetailView({ symbol }: { symbol: string }) {
  const detail = useApi((signal) => api.stock(symbol, signal), [symbol]);
  const [removed, setRemoved] = useState<RemoveOut | null>(null);

  useEffect(() => {
    document.title = `${symbol} · stockMarket`;
    return () => {
      document.title = "stockMarket";
    };
  }, [symbol]);

  if (detail.errorStatus === 404) {
    return (
      <Missing
        title={`${symbol} isn't a tracked company`}
        hint={`Add it from the dashboard's "Add a company" box, or with: python -m jobs.add_company ${symbol}. The nightly refresh keeps it current after that.`}
      />
    );
  }

  if (removed) {
    const { kept } = removed;
    return (
      <Missing
        title={`${symbol} is no longer tracked`}
        hint={`${removed.message} Still stored: ${kept.prices.toLocaleString()} daily prices, ${kept.filings.toLocaleString()} filings, ${kept.headlines.toLocaleString()} headlines, ${kept.figures.toLocaleString()} financial figures.`}
      />
    );
  }

  const stock = detail.data;
  return (
    <>
      <nav className="crumbs">
        <Link to="/">← Dashboard</Link>
      </nav>

      <header className="stock-head">
        <div>
          <h1 className="page-title">{symbol}</h1>
          <p className="muted">{stock?.name ?? (detail.loading ? "Loading…" : "")}</p>
        </div>
        {stock && (
          <div className="stock-price">
            <span className="big-price">{formatPrice(stock.last_price)}</span>
            <span className={`day-change ${directionOf(stock.change_pct)}`}>{formatChangePct(stock.change_pct)} today</span>
          </div>
        )}
      </header>
      {detail.error && (
        <p role="alert" className="error">
          {detail.error} <button onClick={detail.reload}>Try again</button>
        </p>
      )}

      <div className="detail-grid">
        <div className="col">
          <PriceHistory symbol={symbol} />
          <CopilotBox symbol={symbol} examples={EXAMPLES} />
          <FilingsList symbol={symbol} />
        </div>
        <div className="col">
          {stock && <KeyStats stock={stock} />}
          <Fundamentals symbol={symbol} />
          <NewsPanel symbol={symbol} />
        </div>
      </div>
      {stock && <RemoveCompany symbol={symbol} name={stock.name} onRemoved={setRemoved} />}
    </>
  );
}
