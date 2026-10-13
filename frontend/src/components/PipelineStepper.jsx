const STAGE_LABELS = {
  ingest: "Ingest",
  normalize: "Normalize",
  deduplicate: "Deduplicate",
  resolve_institutions: "Resolve institutions",
  edges_mentions: "Build edges & mentions",
  classify: "Classify",
  metrics_integrity: "Metrics & integrity",
  evidence_hashing: "Evidence & hashing",
  reports: "Reports",
};

const STAGE_ORDER = Object.keys(STAGE_LABELS);

function fmtCounts(counts) {
  if (!counts || typeof counts !== "object") return null;
  const parts = Object.entries(counts)
    .filter(([, v]) => typeof v === "number")
    .slice(0, 4)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v.toLocaleString()}`);
  return parts.length ? parts.join(" · ") : null;
}

export default function PipelineStepper({ job }) {
  if (!job) return null;
  const stages = job.stages || {};
  return (
    <div className="panel panel-pad">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-neutral-900">Pipeline</h3>
        <span
          className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
            job.status === "completed"
              ? "border-teal-200 bg-teal-50 text-teal-700"
              : "border-amber-300 bg-amber-50 text-amber-800"
          }`}
        >
          {job.status}
        </span>
      </div>
      <ol className="space-y-2">
        {STAGE_ORDER.map((stage, i) => {
          const counts = stages[stage];
          const done = counts !== undefined;
          return (
            <li key={stage} className="flex items-start gap-3">
              <span
                className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${
                  done ? "border-teal-600 bg-teal-50 text-teal-700" : "border-neutral-300 text-neutral-500"
                }`}
              >
                {done ? "✓" : i + 1}
              </span>
              <div className="min-w-0">
                <p className={`text-sm font-medium ${done ? "text-neutral-900" : "text-neutral-500"}`}>
                  {STAGE_LABELS[stage]}
                </p>
                {done && <p className="text-xs text-neutral-500">{fmtCounts(counts) || "done"}</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
