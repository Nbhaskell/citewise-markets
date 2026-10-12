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
          <CopilotBox />
        </div>
        <div className="col">
          <NewsPanel />
        </div>
      </div>
    </>
  );
}
