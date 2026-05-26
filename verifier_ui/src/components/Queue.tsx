import type { PendingDecision } from "../lib/api";

interface Props {
  decisions: PendingDecision[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function Queue({ decisions, selectedId, onSelect }: Props) {
  if (decisions.length === 0) {
    return (
      <div className="queue queue-empty">
        <p className="muted">No pending decisions.</p>
        <p className="muted-faint">
          Run the agent in another terminal:
          <br />
          <code>uv run python -m agent.main --demo</code>
        </p>
      </div>
    );
  }
  return (
    <ol className="queue">
      {decisions.map((d) => (
        <li
          key={d.decision_id}
          className={d.decision_id === selectedId ? "queue-item active" : "queue-item"}
          onClick={() => onSelect(d.decision_id)}
        >
          <div className="queue-item-name" dir="auto">{d.candidate_name}</div>
          <div className="queue-item-meta">
            <span className="badge badge-small">{d.seeker_language.toUpperCase()}</span>
            <span className="muted-faint">{(d.confidence * 100).toFixed(0)}%</span>
          </div>
        </li>
      ))}
    </ol>
  );
}
