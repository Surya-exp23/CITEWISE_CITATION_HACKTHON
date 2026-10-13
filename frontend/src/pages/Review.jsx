import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import MergeCompare from "../components/MergeCompare";
import { EmptyState, ErrorBox, Skeleton } from "../components/ui";

function AiChip({ itemId }) {
  const [sugg, setSugg] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchSuggestion = async () => {
    setLoading(true);
    try {
      setSugg(await api.get(`/review/${itemId}/suggestion`));
    } catch {
      setSugg({ ai_suggestion: { same_paper: false, confidence: 0, reason: "failed to load" }, llm_enabled: false });
    } finally {
      setLoading(false);
    }
  };

  if (!sugg && !loading) {
    return (
      <button className="btn-ghost py-1.5! px-3! text-xs" onClick={fetchSuggestion}>
        ✦ Ask AI co-pilot
      </button>
    );
  }
  if (loading) return <span className="text-xs text-neutral-500">Consulting AI…</span>;
  const s = sugg.ai_suggestion || {};
  return (
    <div className="rounded-lg border border-teal-200 bg-teal-50 p-3 text-sm max-w-xl">
      <p className="text-xs uppercase tracking-wider text-teal-700 mb-1">AI suggestion</p>
      {!sugg.llm_enabled && (
        <p className="text-xs text-neutral-500 mb-1">
          LLM assist is off (set ENABLE_LLM_ASSIST=true + GROQ_API_KEY to enable).
        </p>
      )}
      <p className="text-neutral-800">
        <span className={`font-semibold ${s.same_paper ? "text-teal-700" : "text-amber-700"}`}>
          {s.same_paper ? "Same paper" : "Different papers"}
        </span>
        <span className="text-neutral-500"> · confidence {(s.confidence ?? 0).toFixed(2)}</span>
      </p>
      {s.reason && <p className="text-neutral-500 mt-1">{s.reason}</p>}
      <p className="text-[11px] text-neutral-600 mt-1">Advisory only — a human makes the decision.</p>
    </div>
  );
}

export default function Review() {
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deciding, setDeciding] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await api.get("/review?status=pending&page=1&page_size=50"));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const decide = async (itemId, decision) => {
    setDeciding(itemId);
    try {
      await api.post(`/review/${itemId}/decision`, { decision });
      setItems((prev) => prev.filter((i) => i.id !== itemId));
    } catch (e) {
      setError(e.message);
    } finally {
      setDeciding(null);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="text-sm text-neutral-500">
        <Link className="link-teal" to="/">Overview</Link> / Review queue
      </div>
      <div>
        <h1 className="text-2xl font-bold">Review queue</h1>
        <p className="text-neutral-500 text-sm mt-1">
          Uncertain merges are never applied silently. A human approves or rejects each pair —
          rejections are remembered and the pair is never auto-merged again.
        </p>
      </div>

      {error && <ErrorBox message={error} onRetry={load} />}

      {loading && (
        <div className="space-y-3"><Skeleton className="h-48" /><Skeleton className="h-48" /></div>
      )}

      {!loading && items && items.length === 0 && (
        <EmptyState
          title="Queue is empty"
          message="No pending review items. The dedup pipeline merged everything it was confident about."
        />
      )}

      {!loading && items?.map((item) => (
        <div key={item.id} className="space-y-3">
          <MergeCompare item={item} onDecision={decide} deciding={deciding === item.id} />
          <AiChip itemId={item.id} />
        </div>
      ))}
    </div>
  );
}
