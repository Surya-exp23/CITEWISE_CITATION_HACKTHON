export function Skeleton({ className = "h-24" }) {
  return <div className={`skeleton ${className}`} />;
}

export function EmptyState({ title, message, action }) {
  return (
    <div className="panel panel-pad text-center py-10">
      <p className="text-lg font-semibold text-neutral-800">{title}</p>
      {message && <p className="text-sm text-neutral-500 mt-2 max-w-md mx-auto">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorBox({ message, onRetry }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4">
      <p className="text-sm font-semibold text-red-800">Something went wrong</p>
      <p className="text-sm text-red-700 mt-1">{message}</p>
      {onRetry && (
        <button className="btn-ghost mt-3 py-2! px-4! text-sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function SectionTitle({ children, action }) {
  return (
    <div className="flex items-center justify-between mb-3 pb-2 border-b border-neutral-100">
      <h2 className="text-lg font-semibold text-neutral-900">{children}</h2>
      {action}
    </div>
  );
}

export function SyntheticBanner({ syntheticRows }) {
  if (!syntheticRows) return null;
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      <span className="font-semibold">Demo data notice: </span>
      real OpenAlex records plus {syntheticRows.toLocaleString()} deliberately planted
      synthetic rows (duplicate records, repeated in-text mentions, look-alike titles) to demonstrate
      the cleaning pipeline.
    </div>
  );
}

export function HashText({ value, short = 16 }) {
  if (!value) return <span className="text-neutral-400">—</span>;
  const shown = value.length > short * 2 + 3 ? `${value.slice(0, short)}…${value.slice(-short)}` : value;
  return (
    <code className="font-mono text-xs text-neutral-600 break-all" title={value}>
      {shown}
    </code>
  );
}
