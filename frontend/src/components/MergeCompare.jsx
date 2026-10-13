function RecordCard({ record, title }) {
  if (!record) return null;
  return (
    <div className="panel panel-pad flex-1 min-w-0">
      <p className="text-xs uppercase tracking-wider text-neutral-500 mb-2">{title}</p>
      <p className="text-sm font-semibold text-neutral-900 leading-snug">{record.title || "Untitled"}</p>
      <dl className="mt-3 space-y-1.5 text-sm">
        <div className="flex gap-2"><dt className="text-neutral-500 w-20 shrink-0">Record</dt><dd className="font-mono text-xs text-neutral-600 break-all">{record.record_id}</dd></div>
        <div className="flex gap-2"><dt className="text-neutral-500 w-20 shrink-0">DOI</dt><dd className="font-mono text-xs text-neutral-600 break-all">{record.doi || "—"}</dd></div>
        <div className="flex gap-2"><dt className="text-neutral-500 w-20 shrink-0">Year</dt><dd className="text-neutral-600">{record.year ?? "—"}</dd></div>
        <div className="flex gap-2"><dt className="text-neutral-500 w-20 shrink-0">Authors</dt><dd className="text-neutral-600">{record.authors?.join(", ") || "—"}</dd></div>
        <div className="flex gap-2"><dt className="text-neutral-500 w-20 shrink-0">Preprint</dt><dd className="text-neutral-600">{record.is_preprint ? "yes" : "no"}</dd></div>
      </dl>
    </div>
  );
}

function highlightDiff(a, b) {
  if (!a || !b || a === b) return { a, b, same: true };
  return { a, b, same: false };
}

export default function MergeCompare({ item, onDecision, deciding }) {
  const p = item.payload || {};
  const ra = p.record_a || {};
  const rb = p.record_b || {};
  const titles = highlightDiff(ra.title, rb.title);
  return (
    <div className="panel panel-pad">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-sm font-semibold text-neutral-900">
            {item.item_type === "dedup" ? "Possible duplicate records" : item.item_type}
          </p>
          <p className="text-xs text-neutral-500 mt-0.5">
            score {item.score ?? "—"}
            {p.rule && ` · rule ${p.rule}`}
            {p.reasons?.length > 0 && ` · ${p.reasons.join(", ")}`}
          </p>
        </div>
        <span className="rounded-full border border-neutral-300 px-2.5 py-0.5 text-xs text-neutral-500">
          {item.status}
        </span>
      </div>
      <div className="flex flex-col md:flex-row gap-3">
        <RecordCard record={ra} title="Record A" />
        <RecordCard record={rb} title="Record B" />
      </div>
      {!titles.same && (
        <p className="text-xs text-amber-800 mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
          Titles differ — compare carefully before merging.
        </p>
      )}
      {item.status === "pending" && (
        <div className="flex gap-3 mt-4">
          <button className="btn-primary" disabled={deciding} onClick={() => onDecision(item.id, "approve")}>
            {deciding ? "Working…" : "Approve merge"}
          </button>
          <button className="btn-ghost" disabled={deciding} onClick={() => onDecision(item.id, "reject")}>
            Reject (never merge again)
          </button>
        </div>
      )}
    </div>
  );
}
