import { useId, useState } from "react";
import type { CopilotResponse } from "../api/types";
import { safeHttpUrl } from "../lib/format";
import { AnswerText } from "./AnswerText";

/**
 * One copilot answer: the text with clickable citations, warnings, and the numbered sources.
 * It owns its own "which source is highlighted" state and unique element ids, so many answers can sit on one page.
 */
export function AnswerView({ result }: { result: CopilotResponse }) {
  const uid = useId();
  const [highlight, setHighlight] = useState<number | null>(null);
  const uncited = !result.refused && !result.grounded;
  // No company named or chosen: the search covered every company, so say which ones the answer really used.
  const unnamed = !result.refused && result.companies.length === 0 && result.sources.length > 0;
  const drewOn = [...new Set(result.sources.map((src) => src.symbol))];

  function showSource(n: number) {
    setHighlight(n);
    document.getElementById(`${uid}-source-${n}`)?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }

  return (
    <div className="result">
      <p className="muted small">
        {result.refused
          ? "No matching passages found"
          : result.companies.length > 0
            ? `Searched filings for ${result.companies.join(", ")}`
            : "Searched all stored filings"}
      </p>

      <AnswerText text={result.answer} onCite={showSource} />

      {result.unverified_numbers.length > 0 && (
        <p role="alert" className="flag warn">
          Some figures in this answer weren't found in the cited passages ({result.unverified_numbers.join(", ")}).
          Check the source before relying on them.
        </p>
      )}
      {unnamed && (
        <p className="flag warn">
          No company was named, so this searched every company's filings and drew on {drewOn.join(", ")}. If you meant a
          specific company, name it in your question.
        </p>
      )}
      {uncited && (
        <p role="alert" className="flag warn">
          This answer doesn't cite any filing passages. Treat it as unverified.
        </p>
      )}

      {result.sources.length > 0 && (
        <ol className="sources" aria-label="Sources">
          {result.sources.map((s) => (
            <li
              key={s.number}
              id={`${uid}-source-${s.number}`}
              className={highlight === s.number ? "highlight" : undefined}
              value={s.number}
            >
              <strong>
                {s.symbol} {s.form}
              </strong>{" "}
              filed {s.filed_at}
              {s.section ? ` · ${s.section}` : ""}
              {safeHttpUrl(s.url) && (
                <>
                  {" · "}
                  <a href={safeHttpUrl(s.url)} target="_blank" rel="noopener noreferrer">
                    View filing
                  </a>
                </>
              )}
              <details>
                <summary>Excerpt</summary>
                <p className="excerpt">{s.excerpt}</p>
              </details>
            </li>
          ))}
        </ol>
      )}
      <p className="muted small">{result.disclaimer}</p>
    </div>
  );
}
