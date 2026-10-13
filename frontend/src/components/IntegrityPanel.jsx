const FLAG_TITLES = {
  cites_retracted: "Retracted paper in citation record",
  high_internal_ratio: "High internal citation ratio",
  citation_concentration: "Citation concentration",
  citation_ring: "Possible citation ring",
};

function FlagDetail({ flag }) {
  const d = flag.details || {};
  return (
    <div className="mt-2 text-xs text-neutral-500 space-y-1">
      {d.internal_ratio !== undefined && (
        <p>Internal ratio {(d.internal_ratio * 100).toFixed(1)}% (threshold {(d.threshold * 100).toFixed(0)}%, n={d.unique_citations})</p>
      )}
      {d.concentration !== undefined && (
        <p>
          Top 3 citing authors: {(d.concentration * 100).toFixed(1)}% of citations
          {d.top_citing_authors?.length > 0 && ` — ${d.top_citing_authors.join(", ")}`}
        </p>
      )}
      {d.retracted_citing_citation_ids?.length > 0 && (
        <p>Retracted citing citations: {d.retracted_citing_citation_ids.length}</p>
      )}
      {d.retracted_own_work_ids?.length > 0 && (
        <p>Retracted own works: {d.retracted_own_work_ids.length}</p>
      )}
      {d.ring_author_keys?.length > 0 && <p>Authors: {d.ring_author_keys.join(", ")}</p>}
    </div>
  );
}

export default function IntegrityPanel({ flags }) {
  if (!flags) return null;
  return (
    <div className="panel panel-pad">
      <h3 className="text-base font-semibold text-neutral-900 mb-1">Integrity flags</h3>
      <p className="text-xs text-neutral-500 mb-4">Signals worth reviewing — not accusations.</p>
      {flags.length === 0 && (
        <p className="text-sm text-neutral-500">No integrity flags for this scope. Clean record.</p>
      )}
      <div className="space-y-3">
        {flags.map((f, i) => (
          <div key={i} className="rounded-lg border border-neutral-200 bg-neutral-50 p-3">
            <div className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-amber-500" aria-hidden />
              <p className="text-sm font-medium text-neutral-900">
                {FLAG_TITLES[f.flag_type] || f.flag_type}
              </p>
              {f.severity && (
                <span className="text-[11px] text-neutral-500 border border-neutral-300 rounded-full px-2 py-px">
                  {f.severity}
                </span>
              )}
            </div>
            {f.details?.note && <p className="text-sm text-neutral-500 mt-1">{f.details.note}</p>}
            <FlagDetail flag={f} />
          </div>
        ))}
      </div>
    </div>
  );
}
