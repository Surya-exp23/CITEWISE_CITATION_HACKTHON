import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import KpiCard from "../components/KpiCard";
import PipelineStepper from "../components/PipelineStepper";
import { EmptyState, ErrorBox, SectionTitle, Skeleton, SyntheticBanner } from "../components/ui";

export default function Overview() {
  const [institutions, setInstitutions] = useState(null);
  const [instId, setInstId] = useState(null);
  const [report, setReport] = useState(null);
  const [leaders, setLeaders] = useState(null);
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [ingesting, setIngesting] = useState(false);

  const loadInstitution = useCallback(async (id) => {
    setLoading(true);
    setError(null);
    try {
      const [rep, lb] = await Promise.all([
        api.get(`/institutions/${id}/report`),
        api.get(`/institutions/${id}/researchers?page=1&page_size=20`),
      ]);
      setReport(rep);
      setLeaders(lb);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    api
      .get("/institutions?page=1&page_size=50")
      .then((list) => {
        setInstitutions(list);
        if (list?.length) {
          setInstId(list[0].id);
          loadInstitution(list[0].id);
        } else {
          setLoading(false);
        }
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [loadInstitution]);

  const loadDemo = async () => {
    setIngesting(true);
    try {
      const j = await api.post("/ingest/demo");
      setJob(j);
      if (instId) await loadInstitution(instId);
    } catch (e) {
      setError(e.message);
    } finally {
      setIngesting(false);
    }
  };

  const k = report?.kpis;

  return (
    <div className="space-y-6">
      <section className="panel panel-pad">
        <h1 className="text-3xl font-bold tracking-tight">We don't just give a citation number. We give proof.</h1>
        <p className="text-neutral-500 mt-2 max-w-2xl">
          CiteWise is an AI-assisted verification layer over open citation data. It removes duplicate
          records, collapses repeated mentions, classifies every citation as self, internal, or external —
          and every number drills down to auditable evidence.
        </p>
        <div className="flex flex-wrap items-center gap-3 mt-4">
          <button className="btn-primary" onClick={loadDemo} disabled={ingesting}>
            {ingesting ? "Loading…" : "Load demo data"}
          </button>
          {institutions?.length > 0 && (
            <select
              className="input w-auto!"
              value={instId ?? ""}
              onChange={(e) => {
                const id = Number(e.target.value);
                setInstId(id);
                loadInstitution(id);
              }}
              aria-label="Select institution"
            >
              {institutions.map((i) => (
                <option key={i.id} value={i.id}>{i.name}</option>
              ))}
            </select>
          )}
        </div>
      </section>

      {report?.data_notice?.has_synthetic && (
        <SyntheticBanner syntheticRows={report.data_notice.synthetic_rows} />
      )}

      {job && <PipelineStepper job={job} />}

      {error && <ErrorBox message={error} onRetry={() => instId && loadInstitution(instId)} />}

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" />
        </div>
      ) : (
        k && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard label="Raw citation rows" value={k.raw_rows} sub="as imported" />
            <KpiCard label="Unique citations" value={k.unique_citations} sub="after dedup + mention collapse" />
            <KpiCard label="Verified external" value={k.external} sub={`headline: ${report.policy.headline_metric}`} accent="text-teal-700" />
            <KpiCard label="Verified h-index" value={k.h_index_verified} sub={`raw h-index ${k.h_index_raw}`} />
          </div>
        )
      )}

      <section>
        <SectionTitle>Researcher leaderboard</SectionTitle>
        {!loading && leaders && leaders.length === 0 && (
          <EmptyState title="No researchers yet" message="Load the demo data to populate the leaderboard." />
        )}
        {!loading && leaders && leaders.length > 0 && (
          <div className="panel overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Researcher</th>
                  <th className="text-right">Papers</th>
                  <th className="text-right">Raw citations</th>
                  <th className="text-right">Verified</th>
                  <th className="text-right">h-index</th>
                </tr>
              </thead>
              <tbody>
                {leaders.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link className="link-teal font-medium" to={`/researchers/${r.id}`}>
                        {r.name}
                      </Link>
                    </td>
                    <td className="text-right text-neutral-600">{r.papers}</td>
                    <td className="text-right text-neutral-500">{r.raw_citations}</td>
                    <td className="text-right text-teal-700 font-semibold">{r.verified_citations}</td>
                    <td className="text-right text-neutral-600">{r.h_index_verified}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
