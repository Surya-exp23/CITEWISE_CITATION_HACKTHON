export default function KpiCard({ label, value, sub, onClick, accent }) {
  const clickable = typeof onClick === "function";
  return (
    <button
      type="button"
      disabled={!clickable}
      onClick={onClick}
      className={`panel panel-pad text-left w-full transition-all ${
        clickable ? "hover:border-teal-600 hover:shadow-md cursor-pointer" : "cursor-default"
      }`}
      title={clickable ? "Click to see the underlying citations" : undefined}
    >
      <p className="text-xs uppercase tracking-wider text-neutral-500">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${accent || "text-neutral-900"}`}>
        {value === null || value === undefined ? "—" : value.toLocaleString()}
      </p>
      {sub && <p className="text-xs text-neutral-500 mt-1">{sub}</p>}
    </button>
  );
}
