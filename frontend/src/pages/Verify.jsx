import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import HashVerifier from "../components/HashVerifier";
import { ErrorBox, HashText, Skeleton } from "../components/ui";

// Public verify page — no nav chrome. Anyone with a report link (e.g. from a
// QR code) can check it without trusting CiteWise.
export default function Verify() {
  const { reportId } = useParams();
  const [result, setResult] = useState(null);
  const [sources, setSources] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.get(`/verify/${reportId}`),
      api.get(`/reports/${reportId}`).catch(() => null),
    ])
      .then(([v, payload]) => {
        if (!alive) return;
        setResult(v);
        if (payload?.data_sources) setSources(payload.data_sources);
      })
      .catch((e) => alive && setError(e.message));
    return () => { alive = false; };
  }, [reportId]);

  const match = result?.status === "MATCH";

  return (
    <div className="min-h-screen bg-[#f8fafc] text-neutral-900">
      <div className="max-w-2xl mx-auto px-4 py-10 space-y-6">
        <div className="text-center">
          <p className="text-sm font-bold tracking-tight text-neutral-500">CiteWise</p>
          <h1 className="text-xl font-semibold mt-1">Report verification</h1>
          <p className="text-xs text-neutral-500 mt-1">Report #{reportId}</p>
        </div>

        {error && <ErrorBox message={error} />}

        {!result && !error && (
          <div className="space-y-3"><Skeleton className="h-32" /><Skeleton className="h-48" /></div>
        )}

        {result && (
          <div className={`rounded-xl border-2 p-5 text-center shadow-sm ${match ? "border-teal-600 bg-teal-50" : "border-red-400 bg-red-50"}`}>
            <p className={`text-4xl font-black tracking-tight ${match ? "text-teal-700" : "text-red-700"}`}>
              {result.status}
            </p>
            <p className="text-sm text-neutral-600 mt-2 max-w-md mx-auto">
              {match
                ? "The stored report matches its recomputed evidence hashes. It has not been altered since generation."
                : "Warning: the recomputed hashes do not match the stored root. This report may have been tampered with."}
            </p>
            <div className="mt-4 text-left text-sm space-y-2">
              <p><span className="text-neutral-500">Stored root: </span><HashText value={result.stored_root} /></p>
              <p><span className="text-neutral-500">Recomputed: </span><HashText value={result.recomputed_root} /></p>
              <p className="text-neutral-500">Records: {result.record_count} · Generated: {result.generated_at ? new Date(result.generated_at).toLocaleString() : "—"}</p>
              {sources && <p className="text-neutral-500 text-xs">Sources: {sources.join(" · ")}</p>}
            </div>
            <p className="text-xs text-neutral-600 mt-4">
              Hashes prove the report was not altered after generation and show where each record came
              from. They do not prove upstream databases are correct — every record links to its DOI.
            </p>
          </div>
        )}

        <HashVerifier />

        <p className="text-center text-xs text-neutral-600">
          <Link className="link-teal" to="/">← Back to CiteWise</Link>
        </p>
      </div>
    </div>
  );
}
