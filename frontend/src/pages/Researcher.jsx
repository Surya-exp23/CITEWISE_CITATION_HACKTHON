import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { QRCodeSVG } from "qrcode.react";
import { api, API_BASE } from "../lib/api";
import KpiCard from "../components/KpiCard";
import WaterfallChart from "../components/WaterfallChart";
import CitationDrawer from "../components/CitationDrawer";
import PaperTable from "../components/PaperTable";
import IntegrityPanel from "../components/IntegrityPanel";
import { EmptyState, ErrorBox, HashText, SectionTitle, Skeleton, SyntheticBanner } from "../components/ui";

function barFilter(label, headlineMetric) {
  switch (label) {
    case "Duplicate records removed":
      return { predicate: (c) => (c.duplicates_removed || 0) > 0, label: "citations with duplicate records removed" };
    case "Repeated mentions collapsed":
      return { predicate: (c) => (c.repeats_removed || 0) > 0, label: "citations with repeated mentions collapsed" };
    case "Self-citations":
      return { klass: "self" };
    case "Internal citations":
      return { klass: "internal" };
    default:
      if (label === "Unique citations" || label === "Raw rows") return { label: "all citations in scope" };
      return headlineMetric === "external_plus_internal"
        ? { predicate: (c) => c.klass === "external" || c.klass === "internal", label: "verified (external + internal)" }
        : { klass: "external", label: "verified external citations" };
  }
}

function TimelineChart({ data }) {
  if (!data?.length) return null;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 10, right: 10, bottom: 5, left: -15 }}>
        <CartesianGrid stroke="#e5e7eb" vertical={false} />
        <XAxis dataKey="year" tick={{ fill: "#4b5563", fontSize: 11 }} />
        <YAxis tick={{ fill: "#4b5563", fontSize: 11 }} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 13 }}
          labelStyle={{ color: "#171717" }}
        />
        <Bar dataKey="external" stackId="t" fill="#0d9488" name="external" />
        <Bar dataKey="internal" stackId="t" fill="#6366f1" name="internal" />
        <Bar dataKey="self" stackId="t" fill="#f59e0b" name="self" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function Researcher() {
  const { id } = useParams();
  const [report, setReport] = useState(null);
  const [papers, setPapers] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [drawer, setDrawer] = useState(null);
  const [genReport, setGenReport] = useState(null);
  const [generating, setGenerating] = useState(false);
  const papersRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rep, pap] = await Promise.all([
        api.get(`/researchers/${id}/report`),
        api.get(`/researchers/${id}/papers?page=1&page_size=100`),
      ]);
      setReport(rep);
      setPapers(pap);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const openDrawer = (filter, title) => setDrawer({ filter, title });
  const headline = report?.policy?.headline_metric || "external_only";
  const k = report?.kpis;

  const generate = async () => {
    setGenerating(true);
    try {
      const r = await api.post("/reports", { scope_type: "researcher", scope_id: Number(id) });
      setGenReport(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  };

  const verifiedFilter = () =>
    headline === "external_plus_internal"
      ? { predicate: (c) => c.klass === "external" || c.klass === "internal", label: "verified (external + internal)" }
      : { klass: "external", label: "verified external citations" };

  return (
    <div className="space-y-6">
      <div className="text-sm text-neutral-500">
        <Link className="link-teal" to="/">Overview</Link> / Researcher
      </div>

      {error && <ErrorBox message={error} onRetry={load} />}

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-1/3" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" />
          </div>
          <Skeleton className="h-72" />
        </div>
      ) : report && (
        <>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold">{report.researcher.name}</h1>
              <p className="text-sm text-neutral-500 mt-1">
                {report.researcher.orcid ? `ORCID ${report.researcher.orcid} · ` : ""}
                {report.researcher.institutions?.length || 0} affiliated institution(s) · policy v{report.policy.version}
              </p>
            </div>
            <button className="btn-primary" onClick={generate} disabled={generating}>
              {generating ? "Generating…" : "Generate verified report"}
            </button>
          </div>

          {report.data_notice?.has_synthetic && (
            <SyntheticBanner syntheticRows={report.data_notice.synthetic_rows} />
          )}

          {genReport && (
            <div className="panel panel-pad flex flex-wrap items-center gap-6">
              <div>
                <QRCodeSVG value={`${window.location.origin}/verify/${genReport.id}`} size={96} bgColor="#ffffff" fgColor="#0a0a0a" />
              </div>
              <div className="text-sm space-y-1.5">
                <p className="font-semibold text-neutral-900">Report #{genReport.id} generated</p>
                <p><span className="text-neutral-500">Root hash: </span><HashText value={genReport.root_hash} /></p>
                <div className="flex flex-wrap gap-3 pt-1">
                  <a className="link-teal" href={`${API_BASE}/reports/${genReport.id}/pdf`} target="_blank" rel="noreferrer">
                    Download PDF ↓
                  </a>
                  <Link className="link-teal" to={`/verify/${genReport.id}`}>
                    Open verify page →
                  </Link>
                </div>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard label="Papers" value={k.papers} onClick={() => papersRef.current?.scrollIntoView({ behavior: "smooth" })} />
            <KpiCard label="Raw rows" value={k.raw_rows} sub="as imported" onClick={() => openDrawer({ label: "all citations in scope" }, "Raw rows → citations")} />
            <KpiCard label="Unique citations" value={k.unique_citations} sub="after dedup + collapse" onClick={() => openDrawer({ label: "all unique citations" }, "Unique citations")} />
            <KpiCard label="Verified total" value={k.verified_total} sub={headline} accent="text-teal-700" onClick={() => openDrawer(verifiedFilter(), "Verified citations")} />
            <KpiCard label="Self" value={k.self} sub={`${(k.self_ratio * 100).toFixed(1)}% of unique`} accent="text-amber-700" onClick={() => openDrawer({ klass: "self" }, "Self-citations")} />
            <KpiCard label="Internal" value={k.internal} sub={`${(k.internal_ratio * 100).toFixed(1)}% of unique`} accent="text-indigo-700" onClick={() => openDrawer({ klass: "internal" }, "Internal citations")} />
            <KpiCard label="External" value={k.external} sub="independent citations" accent="text-teal-700" onClick={() => openDrawer({ klass: "external", label: "verified external citations" }, "External citations")} />
            <KpiCard label="h-index" value={k.h_index_verified} sub={`raw ${k.h_index_raw} · i10 ${k.i10_verified}`} />
          </div>

          <div className="panel panel-pad">
            <SectionTitle>Raw → verified waterfall</SectionTitle>
            <p className="text-xs text-neutral-500 mb-2">Click any bar to inspect the underlying citations.</p>
            <WaterfallChart
              bars={report.waterfall}
              onBarClick={(label) => openDrawer(barFilter(label, headline), `Waterfall: ${label}`)}
            />
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            <div className="panel panel-pad">
              <SectionTitle>Citations by year</SectionTitle>
              {report.timeline?.length ? (
                <TimelineChart data={report.timeline} />
              ) : (
                <p className="text-sm text-neutral-500">No timeline data.</p>
              )}
            </div>
            <div className="panel panel-pad">
              <SectionTitle>Top citing institutions</SectionTitle>
              {report.top_citing_institutions?.length ? (
                <div className="space-y-2">
                  {report.top_citing_institutions.slice(0, 8).map((t, i) => (
                    <div key={i} className="flex items-center gap-3 text-sm">
                      <span className="text-neutral-500 w-64 truncate" title={t.name}>{t.name || "Unknown"}</span>
                      <div className="flex-1 h-2 rounded bg-neutral-100 overflow-hidden">
                        <div
                          className="h-full bg-teal-600"
                          style={{ width: `${(t.count / report.top_citing_institutions[0].count) * 100}%` }}
                        />
                      </div>
                      <span className="text-neutral-600 w-8 text-right">{t.count}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-neutral-500">No citing-institution data.</p>
              )}
            </div>
          </div>

          <div ref={papersRef} className="panel panel-pad">
            <SectionTitle>Papers ({papers?.length || 0})</SectionTitle>
            {papers?.length ? (
              <PaperTable papers={papers} scopeType="researcher" scopeId={Number(id)} />
            ) : (
              <EmptyState title="No papers" message="This researcher has no papers in the dataset." />
            )}
          </div>

          <IntegrityPanel flags={report.integrity_flags} />
        </>
      )}

      <CitationDrawer
        open={!!drawer}
        onClose={() => setDrawer(null)}
        scopeType="researcher"
        scopeId={Number(id)}
        title={drawer?.title}
        filter={drawer?.filter}
      />
    </div>
  );
}
