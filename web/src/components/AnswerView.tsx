import { useId, useState } from "react";
import type { CopilotResponse, CopilotSource } from "../api/types";
import { safeHttpUrl } from "../lib/format";
import { AnswerText } from "./AnswerText";

type Kind = CopilotSource["kind"];

/** Words, not colours, say what kind of source each one is. */
const KIND_LABEL: Record<Kind, string> = {
  filing: "Filing",
  price: "Price data",
  headline: "Headline",
  sentiment: "Sentiment",
  fundamentals: "Financial figures",
};
const LOOKED_AT: Record<Kind, string> = {
  filing: "filings",
  price: "prices",
  headline: "headlines",
  sentiment: "headline sentiment",
  fundamentals: "financial figures",
};
const LINK_LABEL: Partial<Record<Kind, string>> = { filing: "View filing", headline: "Read headline" };

function joinWords(words: string[]): string {
  if (words.length <= 1) return words.join("");
  return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

/** What the model was shown, in a sentence. Filings only keeps the wording the app has always used. */
function lookedAt(result: CopilotResponse): string {
  if (result.refused) return "No matching data found";
  const where = result.companies.length > 0 ? result.companies.join(", ") : null;
  const kinds = result.evidence_kinds;
  if (kinds.length === 1 && kinds[0] === "filing") {
    return where ? `Searched filings for ${where}` : "Searched all stored filings";
  }
  const what = joinWords(kinds.map((k) => LOOKED_AT[k]));
  return where ? `Looked at ${what} for ${where}` : `Looked at ${what}`;
}

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
      <p className="muted small">{lookedAt(result)}</p>

      <AnswerText text={result.answer} onCite={showSource} />

      {result.unverified_numbers.length > 0 && (
        <p role="alert" className="flag warn">
          Some figures in this answer weren't found in the cited sources, or describe a price move the wrong way (
          {result.unverified_numbers.join(", ")}). Check the source before relying on them.
        </p>
      )}
      {result.cautions.map((caution) => (
        <p key={caution} role="alert" className="flag warn">
          {caution}
        </p>
      ))}
      {unnamed && (
        <p className="flag warn">
          No company was named, so this searched every company's filings and drew on {drewOn.join(", ")}. If you meant a
          specific company, name it in your question.
        </p>
      )}
      {uncited && (
        <p role="alert" className="flag warn">
          This answer doesn't cite any source. Treat it as unverified.
        </p>
      )}

      {result.sources.length > 0 && (
        <ol className="sources" aria-label="Sources">
          {result.sources.map((s) => {
            const href = safeHttpUrl(s.url);
            const linkLabel = LINK_LABEL[s.kind];
            return (
              <li
                key={s.number}
                id={`${uid}-source-${s.number}`}
                className={highlight === s.number ? "highlight" : undefined}
                value={s.number}
              >
                <strong>{KIND_LABEL[s.kind]}</strong> {s.title}
                {s.section ? ` · ${s.section}` : ""}
                {href && linkLabel && (
                  <>
                    {" · "}
                    <a href={href} target="_blank" rel="noopener noreferrer">
                      {linkLabel}
                    </a>
                  </>
                )}
                <details>
                  <summary>Excerpt</summary>
                  <p className="excerpt">{s.excerpt}</p>
                </details>
              </li>
            );
          })}
        </ol>
      )}
      <p className="muted small">{result.disclaimer}</p>
    </div>
  );
}
