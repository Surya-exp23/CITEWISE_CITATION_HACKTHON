const STYLES = {
  self: "bg-amber-100 text-amber-800 border-amber-300",
  internal: "bg-indigo-100 text-indigo-800 border-indigo-300",
  external: "bg-teal-100 text-teal-800 border-teal-300",
};

export default function ClassBadge({ klass }) {
  if (!klass) return <span className="text-neutral-500 text-xs">unclassified</span>;
  const style = STYLES[klass] || "bg-neutral-100 text-neutral-700 border-neutral-300";
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${style}`}>
      {klass}
    </span>
  );
}
