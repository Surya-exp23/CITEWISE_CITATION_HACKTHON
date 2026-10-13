import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";

/** What the pipeline found: merges, citations, review items + where to go next. */
export default function IngestSummary({ job }) {
  const [institutions, setInstitutions] = useState([]);
  const [loadingInst, setLoadingInst] = useState(true);

  useEffect(() => {
    let alive = true;
    api
      .get("/institutions?page=1&page_size=50")
      .then((d) => {
        if (alive) setInstitutions(Array.isArray(d) ? d : d.items || []);
      })
      .catch(() => {})
      .finally(() => alive && setLoadingInst(false));
    return () => {
      alive = false;
    };
  }, [job]);

  if (!job || job.status !== "completed") return null;
  const s = job.stages || {};
  const ing = s.ingest || {};
  const ded = s.deduplicate || {};
  const edges = s.edges_mentions || {};
  const cls = s.classify || {};
  const inst = s.resolve_institutions || {};

  const merges = ["exact_id", "title_year_author_hash", "fuzzy_title", "semantic_title", "preprint_to_published", "manual"]
    .map((k) => ({ reason: k, n: ded[k] || 0 }))
    .filter((m) => m.n > 0);
  const totalMerged = merges.reduce((a, m) => a + m.n, 0);
  const reviewQueued = (ded.queued || 0) + (inst.affiliation_review_queued || 0);

  const stats = [
    { label: "Raw rows in", value: ing.raw_citation_rows ?? ing.raw_works ?? "–" },
    { label: "Canonical works", value: ded.works ?? "–" },
    { label: "Duplicates merged", value: totalMerged },
    { label: "Unique citations", value: edges.edges ?? "–" },
    { label: "Needs human review", value: reviewQueued, highlight: reviewQueued > 0 },
  ];

  return (
    <div className="panel panel-pad">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-neutral-900">What the pipeline found</h3>
        <span className="rounded-full border border-teal-200 bg-teal-50 px-2.5 py-0.5 text-xs font-semibold text-teal-700">
          ingest complete
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5 mb-4">
        {stats.map((st) => (
          <div
            key={st.label}
            className={`rounded-xl border p-3 ${
              st.highlight ? "border-amber-300 bg-amber-50" : "border-neutral-200 bg-white"
            }`}
          >
            <div className={`text-2xl font-bold ${st.highlight ? "text-amber-800" : "text-neutral-900"}`}>
              {typeof st.value === "number" ? st.value.toLocaleString() : st.value}
            </div>
            <div className="text-xs text-neutral-500 mt-0.5">{st.label}</div>
          </div>
        ))}
      </div>

      {merges.length > 0 && (
        <p className="text-sm text-neutral-600 mb-2">
          Merges: {merges.map((m) => `${m.n} × ${m.reason.replace(/_/g, " ")}`).join(" · ")}
        </p>
      )}
      {(cls.self != null || cls.external != null) && (
        <p className="text-sm text-neutral-600 mb-4">
          Citations: <span className="font-medium text-amber-700">{cls.self || 0} self</span>
          {" · "}
          <span className="font-medium text-indigo-700">{cls.internal || 0} internal</span>
          {" · "}
          <span className="font-medium text-teal-700">{cls.external || 0} external</span>
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-neutral-100">
        {reviewQueued > 0 ? (
          <Link to="/review" className="btn-primary">
            Review queue ({reviewQueued})
          </Link>
        ) : (
          <span className="text-sm text-neutral-500">No items need human review.</span>
        )}
        {!loadingInst && institutions.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-neutral-500">Browse:</span>
            {institutions.slice(0, 4).map((i) => (
              <Link key={i.id} to={`/institutions/${i.id}`} className="link-teal font-medium">
                {i.name}
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
