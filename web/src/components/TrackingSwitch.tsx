/**
 * An on/off switch for "is this company tracked". The state is in words as well as the ✓ / ✕ and the position of the knob, never in
 * color alone. It only asks to be toggled: the caller shows a confirmation before anything happens.
 */
export function TrackingSwitch({
  symbol,
  tracked,
  busy = false,
  disabled = false,
  onToggle,
}: {
  symbol: string;
  tracked: boolean;
  /** An update is running for this company: the switch shows "Updating…" and can't be pressed. */
  busy?: boolean;
  disabled?: boolean;
  onToggle: () => void;
}) {
  const word = busy ? "Updating…" : tracked ? "Tracked" : "Not tracked";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={tracked}
      aria-label={`${symbol}: ${busy ? "updating" : tracked ? "tracked" : "not tracked"}`}
      className={`tracking-switch ${tracked ? "on" : "off"}`}
      disabled={disabled || busy}
      onClick={onToggle}
    >
      <span className="switch-track" aria-hidden="true">
        <span className="switch-mark">{tracked ? "✓" : "✕"}</span>
        <span className="switch-knob" />
      </span>
      <span className="switch-word">{word}</span>
    </button>
  );
}
