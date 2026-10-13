import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import PipelineStepper from "../components/PipelineStepper";
import IngestSummary from "../components/IngestSummary";
import { ErrorBox, SectionTitle } from "../components/ui";

const EXPECTED_COLUMNS = [
  "citing_title", "citing_doi", "citing_year", "citing_authors", "citing_affiliations",
  "cited_title", "cited_doi", "cited_year", "cited_authors", "context_sentence",
];

export default function Ingest() {
  const [job, setJob] = useState(null);
  const [csvResult, setCsvResult] = useState(null);
  const [error, setError] = useState(null);
  const [working, setWorking] = useState(false);

  const loadDemo = async () => {
    setWorking(true);
    setError(null);
    try {
      setJob(await api.post("/ingest/demo"));
    } catch (e) {
      setError(e.message);
    } finally {
      setWorking(false);
    }
  };

  const uploadCsv = async (file) => {
    if (!file) return;
    setWorking(true);
    setError(null);
    setCsvResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api.postForm("/ingest/csv", form);
      setCsvResult(res);
      setJob(res.job);
    } catch (e) {
      setError(e.message);
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="text-sm text-neutral-500">
        <Link className="link-teal" to="/">Overview</Link> / Ingest
      </div>
      <div>
        <h1 className="text-2xl font-bold">Ingest</h1>
        <p className="text-neutral-500 text-sm mt-1">
          Load the cached demo dataset or upload your own CSV. The full 9-stage pipeline runs on every ingest.
        </p>
      </div>

      <div className="panel panel-pad">
        <SectionTitle>Demo dataset</SectionTitle>
        <p className="text-sm text-neutral-500 mb-3">
          Real OpenAlex records (AIIMS New Delhi) with deliberately planted synthetic noise — duplicates,
          repeated mentions, look-alike titles — so the cleaning pipeline has something visible to clean.
        </p>
        <button className="btn-primary" onClick={loadDemo} disabled={working}>
          {working ? "Running pipeline…" : "Load demo data"}
        </button>
      </div>

      <div className="panel panel-pad">
        <SectionTitle>CSV upload</SectionTitle>
        <p className="text-sm text-neutral-500 mb-3">
          Expected columns: <code className="text-xs text-neutral-600">{EXPECTED_COLUMNS.join(", ")}</code>
        </p>
        <input
          type="file"
          accept=".csv"
          disabled={working}
          onChange={(e) => uploadCsv(e.target.files?.[0])}
          className="block w-full text-sm text-neutral-500 file:mr-4 file:rounded-lg file:border file:border-neutral-300 file:bg-neutral-100 file:px-4 file:py-2 file:text-sm file:font-medium file:text-neutral-700 hover:file:bg-neutral-200 file:cursor-pointer"
        />
        {csvResult && (
          <div className="mt-3 text-sm text-neutral-600">
            <p>Rows received: {csvResult.rows_received} · loaded: {csvResult.rows_loaded}</p>
            {csvResult.errors?.length > 0 && (
              <div className="mt-2 max-h-32 overflow-y-auto rounded border border-neutral-200 p-2">
                {csvResult.errors.slice(0, 20).map((er, i) => (
                  <p key={i} className="text-xs text-amber-800">
                    row {er.row}: {er.message}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {error && <ErrorBox message={error} />}
      {job && <PipelineStepper job={job} />}
      {job && <IngestSummary job={job} />}
    </div>
  );
}
