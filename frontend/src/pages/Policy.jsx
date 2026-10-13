import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { ErrorBox, SectionTitle, Skeleton } from "../components/ui";

const SELECT_FIELDS = [
  { key: "citing_authors_considered", label: "Which citing authors count", options: ["any", "first_last"],
    hint: "first_last: only first/last authors can make a citation internal" },
  { key: "self_citation_scope", label: "Self-citation scope", options: ["author", "any_shared_author"],
    hint: "author: only the subject researcher · any_shared_author: any co-author overlap" },
  { key: "headline_metric", label: "Headline metric", options: ["external_only", "external_plus_internal"],
    hint: "Which citations count as verified" },
];

const NUMBER_FIELDS = [
  { key: "dedup_auto_threshold", label: "Dedup auto-merge threshold", min: 50, max: 100, step: 1 },
  { key: "dedup_review_min", label: "Dedup review minimum", min: 0, max: 100, step: 1 },
  { key: "ring_min_mutual_citations", label: "Ring: min mutual citations", min: 1, max: 20, step: 1 },
  { key: "internal_ratio_flag_threshold", label: "Internal-ratio flag threshold", min: 0, max: 1, step: 0.05 },
  { key: "concentration_flag_threshold", label: "Concentration flag threshold", min: 0, max: 1, step: 0.05 },
];

export default function Policy() {
  const [policies, setPolicies] = useState(null);
  const [policyId, setPolicyId] = useState(null);
  const [config, setConfig] = useState({});
  const [version, setVersion] = useState(null);
  const [instId, setInstId] = useState(null);
  const [before, setBefore] = useState(null);
  const [after, setAfter] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([api.get("/policies"), api.get("/institutions?page=1&page_size=50")])
      .then(([plist, ilist]) => {
        setPolicies(plist);
        const active = plist.find((p) => p.is_active) || plist[0];
        if (active) {
          setPolicyId(active.id);
          setConfig(active.config || {});
          setVersion(active.version);
        }
        if (ilist?.length) setInstId(ilist[0].id);
      })
      .catch((e) => setError(e.message));
  }, []);

  const pickPolicy = (id) => {
    const p = policies.find((x) => x.id === Number(id));
    if (p) {
      setPolicyId(p.id);
      setConfig(p.config || {});
      setVersion(p.version);
      setBefore(null);
      setAfter(null);
    }
  };

  const snapshot = async () => {
    if (!instId) return null;
    const rep = await api.get(`/institutions/${instId}/report`);
    const k = rep.kpis;
    return { verified_total: k.verified_total, external: k.external, internal: k.internal, self: k.self, unique: k.unique_citations };
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      setBefore(await snapshot());
      const updated = await api.put(`/policies/${policyId}`, { config });
      setConfig(updated.config || {});
      setVersion(updated.version);
      setAfter(await snapshot());
      const plist = await api.get("/policies");
      setPolicies(plist);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const set = (key, value) => setConfig((c) => ({ ...c, [key]: value }));

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="text-sm text-neutral-500">
        <Link className="link-teal" to="/">Overview</Link> / Policy engine
      </div>
      <div>
        <h1 className="text-2xl font-bold">Policy engine</h1>
        <p className="text-neutral-500 text-sm mt-1">
          Define what counts as internal. Saving recomputes every classification live and bumps the policy version.
        </p>
      </div>

      {error && <ErrorBox message={error} />}

      {!policies && <Skeleton className="h-64" />}

      {policies && (
        <>
          <div className="panel panel-pad">
            <div className="flex items-center gap-3 mb-4">
              <label className="text-sm text-neutral-500">Policy</label>
              <select className="input w-auto!" value={policyId ?? ""} onChange={(e) => pickPolicy(e.target.value)}>
                {policies.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name || `Policy ${p.id}`} (v{p.version}){p.is_active ? " · active" : ""}
                  </option>
                ))}
              </select>
              {version !== null && <span className="text-xs text-neutral-500">version {version}</span>}
            </div>

            <div className="space-y-4">
              {SELECT_FIELDS.map((f) => (
                <div key={f.key}>
                  <label className="text-sm font-medium text-neutral-800">{f.label}</label>
                  <div className="flex gap-2 mt-1.5">
                    {f.options.map((opt) => (
                      <button
                        key={opt}
                        onClick={() => set(f.key, opt)}
                        className={`rounded-lg border px-3 py-1.5 text-sm font-mono ${
                          config[f.key] === opt
                            ? "border-teal-500 bg-teal-50 text-teal-800"
                            : "border-neutral-300 text-neutral-500 hover:border-neutral-500"
                        }`}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-neutral-500 mt-1">{f.hint}</p>
                </div>
              ))}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {NUMBER_FIELDS.map((f) => (
                  <div key={f.key}>
                    <label className="text-sm font-medium text-neutral-800">{f.label}</label>
                    <input
                      type="number"
                      className="input mt-1.5"
                      min={f.min}
                      max={f.max}
                      step={f.step}
                      value={config[f.key] ?? ""}
                      onChange={(e) => set(f.key, Number(e.target.value))}
                    />
                  </div>
                ))}
              </div>
            </div>

            <button className="btn-primary mt-6" onClick={save} disabled={saving}>
              {saving ? "Recomputing…" : "Save & recompute live"}
            </button>
          </div>

          {before && after && (
            <div className="panel panel-pad">
              <SectionTitle>Impact preview — before vs after</SectionTitle>
              <table className="data-table">
                <thead>
                  <tr><th>Metric</th><th className="text-right">Before</th><th className="text-right">After</th><th className="text-right">Δ</th></tr>
                </thead>
                <tbody>
                  {Object.keys(before).map((m) => {
                    const d = after[m] - before[m];
                    return (
                      <tr key={m}>
                        <td className="text-neutral-600">{m.replace(/_/g, " ")}</td>
                        <td className="text-right text-neutral-500">{before[m].toLocaleString()}</td>
                        <td className="text-right text-neutral-900 font-semibold">{after[m].toLocaleString()}</td>
                        <td className={`text-right font-mono ${d === 0 ? "text-neutral-500" : d > 0 ? "text-teal-700" : "text-red-700"}`}>
                          {d > 0 ? "+" : ""}{d.toLocaleString()}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="text-xs text-neutral-500 mt-3">
                Try flipping “which citing authors count” from any → first_last: citations that only match on a
                middle author flip from internal to external.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
