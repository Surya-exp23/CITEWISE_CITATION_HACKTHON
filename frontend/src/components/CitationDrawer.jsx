import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { sha256Hex, canonicalJson } from "../lib/hash";
import { explainClassification, explainIntent, intentLabel } from "../lib/explain";
import ClassBadge from "./ClassBadge";
import { EmptyState, ErrorBox, HashText, Skeleton } from "./ui";

const KLASS_FILTERS = ["all", "self", "internal", "external"];

function useEscape(onClose) {
  useEffect(() => {
    const h = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
}

function EvidenceDetail({ citation, scopeType, scopeId, evidenceRecord }) {
  const [detail, setDetail] = useState(evidenceRecord ? { record: evidenceRecord } : null);
  const [loading, setLoading] = useState(!evidenceRecord);
  const [error, setError] = useState(null);
  const [leaf, setLeaf] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (evidenceRecord) {
      setDetail({ record: evidenceRecord });
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    api
      .get(`/citations/${citation.id}/evidence?scope_type=${scopeType}&scope_id=${scopeId}`)
      .then((d) => alive && setDetail(d))
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [citation.id, scopeType, scopeId, evidenceRecord]);

  useEffect(() => {
    if (!detail?.record) return;
    let alive = true;
    sha256Hex(canonicalJson(detail.record)).then((h) => alive && setLeaf(h));
    return () => { alive = false; };
  }, [detail]);

  if (loading) return <Skeleton className="h-24 mt-3" />;
  if (error) return <p className="text-sm text-red-700 mt-3">{error}</p>;
  const rec = detail.record;
  const klass = rec.class || citation.klass;
  const sentences = rec.context_sentences || [];
  const copyHash = async () => {
    try {
      await navigator.clipboard.writeText(detail.sha256 || leaf || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard unavailable */ }
  };
  return (
    <div className="mt-3 rounded-lg border border-neutral-200 bg-neutral-50 p-3 text-sm space-y-2">
      <p className="text-neutral-600">{explainClassification(klass, rec.reason)}</p>
      {rec.intent && (
        <p className="text-neutral-500">
          <span className="text-neutral-500">AI intent:</span> {intentLabel(rec.intent)} — {explainIntent(rec.intent)}
        </p>
      )}
      {citation.mention_count > 1 && (
        <p className="text-neutral-500">
          <span className="text-teal-700 font-semibold">{citation.mention_count} mentions</span> in this
          citing paper → counted as exactly <span className="font-semibold text-neutral-900">1 citation</span>.
        </p>
      )}
      {sentences.slice(0, 3).map((s, i) => (
        <blockquote key={i} className="border-l-2 border-neutral-300 pl-3 text-neutral-500 italic">
          “{s}”
        </blockquote>
      ))}
      <div className="flex flex-wrap gap-3 text-xs">
        {rec.links?.citing && (
          <a className="link-teal" href={rec.links.citing} target="_blank" rel="noreferrer">
            Citing paper DOI ↗
          </a>
        )}
        {rec.links?.cited && (
          <a className="link-teal" href={rec.links.cited} target="_blank" rel="noreferrer">
            Cited paper DOI ↗
          </a>
        )}
      </div>
      <p className="text-xs text-neutral-500">
        Rule: <code className="text-neutral-500">{rec.reason?.rule || "—"}</code>
        {" · "}raw rows {rec.raw_rows_total}, duplicates removed {rec.duplicates_removed}, repeats removed {rec.repeats_removed}
      </p>
      <div className="flex items-center gap-2">
        <HashText value={detail.sha256 || leaf} />
        <button onClick={copyHash} className="text-xs text-neutral-500 hover:text-teal-700">
          {copied ? "Copied!" : "Copy hash"}
        </button>
      </div>
    </div>
  );
}

function CitationRow({ citation, scopeType, scopeId, evidenceRecord }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-neutral-200 py-3">
      <button className="w-full text-left" onClick={() => setOpen((o) => !o)}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-neutral-900 leading-snug">
              {citation.citing_title || "Untitled"}
            </p>
            <p className="text-xs text-neutral-500 mt-1">
              {citation.year || "—"}
              {citation.mention_count > 1 && (
                <span className="ml-2 text-neutral-500">
                  {citation.mention_count} mentions → counted once
                </span>
              )}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            <ClassBadge klass={citation.klass} />
            {citation.intent && (
              <span className="text-[11px] text-neutral-500 border border-neutral-300 rounded-full px-2 py-px">
                {intentLabel(citation.intent)}
              </span>
            )}
          </div>
        </div>
      </button>
      {open && (
        <EvidenceDetail
          citation={citation}
          scopeType={scopeType}
          scopeId={scopeId}
          evidenceRecord={evidenceRecord}
        />
      )}
    </div>
  );
}

export default function CitationDrawer({ open, onClose, scopeType, scopeId, title, filter }) {
  const [citations, setCitations] = useState(null);
  const [evidenceById, setEvidenceById] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [klassFilter, setKlassFilter] = useState("all");
  const loadedKey = useRef(null);
  useEscape(onClose);

  useEffect(() => {
    setKlassFilter(filter?.klass || "all");
  }, [filter, open]);

  const load = useCallback(async () => {
    const key = `${scopeType}/${scopeId}`;
    if (loadedKey.current === key) return;
    loadedKey.current = key;
    setLoading(true);
    setError(null);
    try {
      if (scopeType === "researcher") {
        const papers = await api.get(`/researchers/${scopeId}/papers?page=1&page_size=100`);
        const lists = await Promise.all(
          papers.map((p) =>
            api
              .get(`/papers/${p.work_id}/citations?scope_type=researcher&scope_id=${scopeId}&page=1&page_size=200`)
              .catch(() => [])
          )
        );
        const seen = new Map();
        for (const list of lists) for (const c of list) seen.set(c.id, c);
        setCitations([...seen.values()].sort((a, b) => a.id - b.id));
      } else {
        // Institution scope: a generated report's evidence payload carries everything.
        const rep = await api.post("/reports", { scope_type: "institution", scope_id: scopeId });
        const payload = await api.get(`/reports/${rep.id}`);
        const ev = {};
        const rows = (payload.evidence || []).map((r) => {
          ev[r.citation_id] = r;
          return {
            id: r.citation_id,
            citing_title: r.citing?.title,
            cited_title: r.cited?.title,
            year: r.citing?.year,
            mention_count: r.mention_count || 1,
            raw_rows_total: r.raw_rows_total,
            duplicates_removed: r.duplicates_removed,
            repeats_removed: r.repeats_removed,
            klass: r.class,
            intent: r.intent,
          };
        });
        setEvidenceById(ev);
        setCitations(rows);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [scopeType, scopeId]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const filtered = useMemo(() => {
    if (!citations) return null;
    let rows = citations;
    if (typeof filter?.predicate === "function") rows = rows.filter(filter.predicate);
    if (klassFilter !== "all") rows = rows.filter((c) => c.klass === klassFilter);
    return rows;
  }, [citations, klassFilter, filter]);

  if (!open) return null;
  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={title || "Citation evidence"}>
        <div className="flex items-center justify-between border-b border-neutral-200 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-neutral-900">{title || "Citation evidence"}</h2>
            {filtered && (
              <p className="text-xs text-neutral-500 mt-0.5">
                {filtered.length} citations{filter?.label ? ` · ${filter.label}` : ""}
              </p>
            )}
          </div>
          <button onClick={onClose} className="btn-ghost px-3! py-1.5! text-sm" aria-label="Close">
            ✕
          </button>
        </div>
        <div className="flex gap-2 px-5 py-3 border-b border-neutral-200">
          {KLASS_FILTERS.map((k) => (
            <button
              key={k}
              onClick={() => setKlassFilter(k)}
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                klassFilter === k
                  ? "border-teal-500 text-teal-700 bg-teal-50"
                  : "border-neutral-300 text-neutral-500 hover:border-neutral-500"
              }`}
            >
              {k === "all" ? "All" : k}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto px-5 pb-6">
          {loading && (
            <div className="space-y-3 mt-4">
              <Skeleton className="h-16" /><Skeleton className="h-16" /><Skeleton className="h-16" />
            </div>
          )}
          {error && <div className="mt-4"><ErrorBox message={error} onRetry={() => { loadedKey.current = null; load(); }} /></div>}
          {!loading && !error && filtered && filtered.length === 0 && (
            <div className="mt-4">
              <EmptyState title="No citations here" message="Nothing in this slice of the data." />
            </div>
          )}
          {!loading && !error && filtered?.map((c) => (
            <CitationRow
              key={c.id}
              citation={c}
              scopeType={scopeType}
              scopeId={scopeId}
              evidenceRecord={evidenceById[c.id]}
            />
          ))}
        </div>
      </aside>
    </>
  );
}
