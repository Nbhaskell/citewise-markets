import { Link } from "react-router-dom";
import { AddCompanyBox } from "../components/AddCompanyBox";
import { ChangesTeaser } from "../components/ChangesTeaser";
import { CopilotBox } from "../components/CopilotBox";
import { FreshnessBar } from "../components/FreshnessBar";
import { NewsPanel } from "../components/NewsPanel";
import { Watchlist } from "../components/Watchlist";

export function Dashboard() {
  return (
    <>
      <FreshnessBar />
      <div className="dashboard-grid">
        <div className="col">
          <Watchlist />
          <AddCompanyBox />
          <CopilotBox />
          <p className="muted small">
            <Link to="/copilot">Open the full-page copilot, with history and a company filter →</Link>
          </p>
        </div>
        <div className="col">
          <ChangesTeaser />
          <NewsPanel />
        </div>
      </div>
    </>
  );
}
