const TOKEN = /(\*\*[^*]+\*\*|\[\d+\])/g;

interface Props {
  text: string;
  onCite: (number: number) => void;
}

/**
 * Shows an answer with each [n] citation as a clickable superscript and **bold** as bold.
 * Everything is rendered as React text, never as HTML, so nothing in the answer can inject markup.
 */
export function AnswerText({ text, onCite }: Props) {
  return (
    <div className="answer">
      {text.split(TOKEN).map((part, i) => {
        const cite = /^\[(\d+)\]$/.exec(part);
        if (cite) {
          const n = Number(cite[1]);
          return (
            <sup key={i}>
              <button className="cite" onClick={() => onCite(n)} aria-label={`Show source ${n}`}>
                {n}
              </button>
            </sup>
          );
        }
        if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
          return <strong key={i}>{part.slice(2, -2)}</strong>;
        }
        return <span key={i}>{part}</span>;
      })}
    </div>
  );
}
