import { useState } from "react";
import { api } from "../lib/api";
import ClassBadge from "./ClassBadge";

function PaperRow({ paper, scopeType, scopeId }) {
  const [open, setOpen] = useState(false);
  const [citations, setCitations] = useState(null);
  const [loading, setLoading] = useState(false);

  const toggle = async () => {
    if (!open && citations === null) {
      setLoading(true);
      try {
        const list = await api.get(
          `/papers/${paper.work_id}/citations?scope_type=${scopeType}&scope_id=${scopeId}&page=1&page_size=200`
        );
        setCitations(list);
      } catch {
        setCitations([]);
      } finally {
        setLoading(false);
      }
    }
    setOpen((o) => !o);
  };

  return (
    <>
      <tr className="cursor-pointer" onClick={toggle}>
        <td>
          <span className="text-neutral-500 mr-2 inline-block w-4">{open ? "▾" : "▸"}</span>
          <span className="font-medium text-neutral-900">{paper.title}</span>
          <div className="text-xs text-neutral-500 mt-0.5 ml-6">
            {paper.year || "—"}
            {paper.doi && (
              <>
                {" · "}
                <a
                  className="link-teal"
                  href={`https://doi.org/${paper.doi}`}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                >
                  {paper.doi}
                </a>
              </>
            )}
          </div>
        </td>
        <td className="text-right text-neutral-600">{paper.unique}</td>
        <td className="text-right text-neutral-600">{paper.verified}</td>
        <td className="text-right">
          <span className="text-amber-700">{paper.self}</span>
          <span className="text-neutral-600"> / </span>
          <span className="text-indigo-700">{paper.internal}</span>
          <span className="text-neutral-600"> / </span>
          <span className="text-teal-700">{paper.external}</span>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={4} className="bg-neutral-50!">
            {loading && <p className="text-sm text-neutral-500 py-2">Loading citations…</p>}
            {!loading && citations && citations.length === 0 && (
              <p className="text-sm text-neutral-500 py-2">No citations recorded for this paper.</p>
            )}
            {!loading && citations && citations.length > 0 && (
              <div className="py-1 space-y-2">
                {citations.map((c) => (
                  <div key={c.id} className="flex items-start justify-between gap-3 text-sm">
                    <div className="min-w-0">
                      <p className="text-neutral-800 truncate">{c.citing_title || "Untitled"}</p>
                      <p className="text-xs text-neutral-500">
                        {c.year || "—"}
                        {c.mention_count > 1 && ` · ${c.mention_count} mentions → counted once`}
                      </p>
                    </div>
                    <ClassBadge klass={c.klass} />
                  </div>
                ))}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

export default function PaperTable({ papers, scopeType, scopeId }) {
  const [sortKey, setSortKey] = useState("verified");
  const [dir, setDir] = useState(-1);
  if (!papers?.length) return null;

  const sorted = [...papers].sort((a, b) => {
    const va = a[sortKey] ?? 0;
    const vb = b[sortKey] ?? 0;
    return (va > vb ? 1 : va < vb ? -1 : 0) * dir;
  });
  const click = (k) => {
    if (sortKey === k) setDir((d) => -d);
    else { setSortKey(k); setDir(-1); }
  };
  const th = (label, k) => (
    <th onClick={() => click(k)} className="cursor-pointer select-none hover:text-neutral-800">
      {label} {sortKey === k ? (dir === -1 ? "↓" : "↑") : ""}
    </th>
  );
  return (
    <div className="overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr>
            <th>Paper</th>
            {th("Unique", "unique")}
            {th("Verified", "verified")}
            <th title="self / internal / external">S / I / E</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => (
            <PaperRow key={p.work_id} paper={p} scopeType={scopeType} scopeId={scopeId} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
