import { useState } from "react";
import type { IterationOut } from "../api/types";

interface TimelineProps {
  iterations: IterationOut[];
}

function outcomeColor(outcome: string): string {
  switch (outcome) {
    case "advanced":
      return "bg-green-500";
    case "reverted":
      return "bg-red-500";
    case "no_changes":
      return "bg-yellow-500";
    case "partial":
      return "bg-orange-500";
    default:
      return "bg-gray-500";
  }
}

function Timeline({ iterations }: TimelineProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // Sort iterations chronologically
  const sorted = [...iterations].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );

  if (sorted.length === 0) {
    return <p className="text-gray-500 text-sm">No iterations to display.</p>;
  }

  return (
    <div data-testid="timeline">
      {/* Horizontal timeline */}
      <div className="flex items-start gap-1 overflow-x-auto pb-4 mb-4">
        {sorted.map((it) => (
          <button
            key={it.id}
            onClick={() => setExpandedId(expandedId === it.id ? null : it.id)}
            className="flex flex-col items-center min-w-[80px] group"
            title={`${it.agent_id} #${it.iteration_num}: ${it.outcome}`}
          >
            <div
              className={`w-4 h-4 rounded-full ${outcomeColor(it.outcome)} group-hover:ring-2 ring-white/30 transition-all ${
                expandedId === it.id ? "ring-2 ring-purple-400" : ""
              }`}
            />
            <div className="w-px h-3 bg-gray-600" />
            <div className="text-center">
              <p className="text-xs font-mono text-gray-400">{it.agent_id}</p>
              <p className="text-xs text-gray-500">#{it.iteration_num}</p>
            </div>
          </button>
        ))}
      </div>

      {/* Expanded detail */}
      {expandedId !== null && (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-4" data-testid="timeline-detail">
          {(() => {
            const it = sorted.find((i) => i.id === expandedId);
            if (!it) return null;
            return (
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm">{it.agent_id}</span>
                  <span className="text-xs text-gray-400">
                    Iteration #{it.iteration_num}
                  </span>
                  <span
                    className={`text-xs font-medium ${
                      it.outcome === "advanced"
                        ? "text-green-400"
                        : it.outcome === "reverted"
                          ? "text-red-400"
                          : "text-yellow-400"
                    }`}
                  >
                    {it.outcome}
                  </span>
                </div>
                <p className="text-sm text-gray-300">{it.hypothesis}</p>
                {it.files_changed.length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500">Files:</p>
                    <ul className="text-xs font-mono text-gray-400">
                      {it.files_changed.map((f) => (
                        <li key={f}>{f}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <p className="text-xs text-gray-500">{it.lesson}</p>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

export default Timeline;
