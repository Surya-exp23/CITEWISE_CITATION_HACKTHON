import { useState } from "react";
import { verifyPayload } from "../lib/hash";
import { ErrorBox, HashText } from "./ui";

// Paste a report payload (GET /api/reports/{id}) and recompute the Merkle root
// locally with Web Crypto — an independent check of the server's claim.
export default function HashVerifier() {
  const [input, setInput] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [working, setWorking] = useState(false);

  const run = async () => {
    setError(null);
    setResult(null);
    let payload;
    try {
      payload = JSON.parse(input);
    } catch {
      setError("That is not valid JSON. Paste the full response of GET /api/reports/{id}.");
      return;
    }
    if (!payload?.evidence || !payload?.root_hash) {
      setError("JSON parsed, but it has no evidence[] or root_hash — paste a full report payload.");
      return;
    }
    setWorking(true);
    try {
      setResult(await verifyPayload(payload));
    } catch (e) {
      setError(e.message);
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="panel panel-pad">
      <h3 className="text-base font-semibold text-neutral-900 mb-1">Independent hash check</h3>
      <p className="text-xs text-neutral-500 mb-3">
        Paste a report payload below. Your browser recomputes every SHA-256 leaf and the Merkle root
        with Web Crypto — the same algorithm the backend uses — and compares it to the stored root hash.
      </p>
      <textarea
        className="input font-mono text-xs"
        rows={6}
        placeholder='{"subject": {...}, "evidence": [...], "root_hash": "..."}'
        value={input}
        onChange={(e) => setInput(e.target.value)}
      />
      <div className="mt-3">
        <button className="btn-primary" onClick={run} disabled={working || !input.trim()}>
          {working ? "Hashing…" : "Verify in browser"}
        </button>
      </div>
      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
      {result && (
        <div className="mt-4 rounded-lg border border-neutral-200 bg-neutral-50 p-4 space-y-2 text-sm">
          <p>
            <span className="text-neutral-500">Result: </span>
            <span className={`font-bold ${result.status === "MATCH" ? "text-teal-700" : "text-red-700"}`}>
              {result.status}
            </span>
          </p>
          <p><span className="text-neutral-500">Stored root: </span><HashText value={result.storedRoot} /></p>
          <p><span className="text-neutral-500">Recomputed: </span><HashText value={result.recomputedRoot} /></p>
          <p className="text-neutral-500">Records hashed: {result.recordCount}</p>
        </div>
      )}
    </div>
  );
}
