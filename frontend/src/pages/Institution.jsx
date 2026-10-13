import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { QRCodeSVG } from "qrcode.react";
import { api, API_BASE } from "../lib/api";
import KpiCard from "../components/KpiCard";
import WaterfallChart from "../components/WaterfallChart";
import CitationDrawer from "../components/CitationDrawer";
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

function YearStack({ data }) {
  if (!data?.length) return null;
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 10, right: 10, bottom: 5, left: -15 }}>
        <CartesianGrid stroke="#e5e7eb" vertical={false} />
        <XAxis dataKey="year" tick={{ fill: "#4b5563", fontSize: 11 }} />
        <YAxis tick={{ fill: "#4b5563", fontSize: 11 }} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 13 }}
          labelStyle={{ color: "#171717" }}
        />
        <Bar dataKey="external" stackId="y" fill="#0d9488" name="external" />
        <Bar dataKey="internal" stackId="y" fill="#6366f1" name="internal" />
        <Bar dataKey="self" stackId="y" fill="#f59e0b" name="self" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function Institution() {
  const { id } = useParams();
  const [report, setReport] = useState(null);
  const [leaders, setLeaders] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [drawer, setDrawer] = useState(null);
  const [sortKey, setSortKey] = useState("verified_citations");
  const [dir, setDir] = useState(-1);
  const [genReport, setGenReport] = useState(null);
  const [generating, setGenerating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rep, lb] = await Promise.all([
        api.get(`/institutions/${id}/report`),
        api.get(`/institutions/${id}/researchers?page=1&page_size=100`),
      ]);
      setReport(rep);
      setLeaders(lb);
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
      const r = await api.post("/reports", { scope_type: "institution", scope_id: Number(id) });
      setGenReport(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  };

  const sortedLeaders = leaders
    ? [...leaders].sort((a, b) => ((a[sortKey] ?? 0) > (b[sortKey] ?? 0) ? 1 : -1) * dir)
    : null;
  const clickSort = (keyName) => {
    if (sortKey === keyName) setDir((d) => -d);
    else { setSortKey(keyName); setDir(-1); }
  };
  const th = (label, keyName, right = true) => (
    <th key={keyName} onClick={() => clickSort(keyName)} className={`cursor-pointer select-none hover:text-neutral-800 ${right ? "text-right" : ""}`}>
      {label} {sortKey === keyName ? (dir === -1 ? "↓" : "↑") : ""}
    </th>
  );

  return (
    <div className="space-y-6">
      <div className="text-sm text-neutral-500">
        <Link className="link-teal" to="/">Overview</Link> / Institution
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
              <h1 className="text-2xl font-bold">{report.institution.name}</h1>
              <p className="text-sm text-neutral-500 mt-1">
                {report.institution.ror && <span className="font-mono text-xs">{report.institution.ror} · </span>}
                policy v{report.policy.version} · headline {report.policy.headline_metric}
              </p>
            </div>
            <button className="btn-primary" onClick={generate} disabled={generating}>
              {generating ? "Generating…" : "Generate report"}
            </button>
          </div>

          {report.data_notice?.has_synthetic && (
            <SyntheticBanner syntheticRows={report.data_notice.synthetic_rows} />
          )}

          {genReport && (
            <div className="panel panel-pad flex flex-wrap items-center gap-6">
              <QRCodeSVG value={`${window.location.origin}/verify/${genReport.id}`} size={96} bgColor="#ffffff" fgColor="#0a0a0a" />
              <div className="text-sm space-y-1.5">
                <p className="font-semibold text-neutral-900">Report #{genReport.id} generated</p>
                <p><span className="text-neutral-500">Root hash: </span><HashText value={genReport.root_hash} /></p>
                <div className="flex flex-wrap gap-3 pt-1">
                  <a className="link-teal" href={`${API_BASE}/reports/${genReport.id}/pdf`} target="_blank" rel="noreferrer">Download PDF ↓</a>
                  <Link className="link-teal" to={`/verify/${genReport.id}`}>Open verify page →</Link>
                </div>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard label="Researchers" value={leaders?.length} />
            <KpiCard label="Raw rows" value={k.raw_rows} onClick={() => openDrawer({ label: "all citations in scope" }, "Raw rows → citations")} />
            <KpiCard label="Unique citations" value={k.unique_citations} onClick={() => openDrawer({ label: "all unique citations" }, "Unique citations")} />
            <KpiCard label="Verified total" value={k.verified_total} accent="text-teal-700"
              onClick={() => openDrawer(barFilter("Verified", headline), "Verified citations")} />
            <KpiCard label="Self" value={k.self} accent="text-amber-700" onClick={() => openDrawer({ klass: "self" }, "Self-citations")} />
            <KpiCard label="Internal" value={k.internal} accent="text-indigo-700" onClick={() => openDrawer({ klass: "internal" }, "Internal citations")} />
            <KpiCard label="External" value={k.external} accent="text-teal-700" onClick={() => openDrawer({ klass: "external" }, "External citations")} />
            <KpiCard label="h-index (verified)" value={k.h_index_verified} sub={`raw ${k.h_index_raw}`} />
          </div>

          <div className="panel panel-pad">
            <SectionTitle>Raw → verified waterfall</SectionTitle>
            <p className="text-xs text-neutral-500 mb-2">Click any bar to inspect the underlying citations.</p>
            <WaterfallChart
              bars={report.waterfall}
              onBarClick={(label) => openDrawer(barFilter(label, headline), `Waterfall: ${label}`)}
            />
          </div>

          <div className="panel panel-pad">
            <SectionTitle>Internal vs external by year</SectionTitle>
            {report.timeline?.length ? <YearStack data={report.timeline} /> : <p className="text-sm text-neutral-500">No timeline data.</p>}
            <div className="flex gap-4 mt-2 text-xs text-neutral-500">
              <span><span className="inline-block h-2 w-2 rounded-full bg-teal-500 mr-1" />external</span>
              <span><span className="inline-block h-2 w-2 rounded-full bg-indigo-500 mr-1" />internal</span>
              <span><span className="inline-block h-2 w-2 rounded-full bg-amber-500 mr-1" />self</span>
            </div>
          </div>

          <div className="panel panel-pad">
            <SectionTitle>Researcher leaderboard</SectionTitle>
            {sortedLeaders?.length ? (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Researcher</th>
                      {th("Papers", "papers")}
                      {th("Raw", "raw_citations")}
                      {th("Verified", "verified_citations")}
                      {th("h-index", "h_index_verified")}
                    </tr>
                  </thead>
                  <tbody>
                    {sortedLeaders.map((r) => (
                      <tr key={r.id}>
                        <td><Link className="link-teal font-medium" to={`/researchers/${r.id}`}>{r.name}</Link></td>
                        <td className="text-right text-neutral-600">{r.papers}</td>
                        <td className="text-right text-neutral-500">{r.raw_citations}</td>
                        <td className="text-right text-teal-700 font-semibold">{r.verified_citations}</td>
                        <td className="text-right text-neutral-600">{r.h_index_verified}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState title="No researchers" message="No affiliated researchers found." />
            )}
          </div>

          <IntegrityPanel flags={report.integrity_flags} />
        </>
      )}

      <CitationDrawer
        open={!!drawer}
        onClose={() => setDrawer(null)}
        scopeType="institution"
        scopeId={Number(id)}
        title={drawer?.title}
        filter={drawer?.filter}
      />
    </div>
  );
}
