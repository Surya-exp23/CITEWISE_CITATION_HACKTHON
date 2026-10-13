import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const COLORS = {
  total: "#0d9488",
  subtotal: "#6366f1",
  negative: "#ef4444",
  positive: "#cbd5e1",
};

function buildSeries(bars) {
  let running = 0;
  return bars.map((b) => {
    const isAnchor = b.subtotal || b.total;
    const base = isAnchor ? 0 : running;
    const delta = b.value;
    const color = b.total ? COLORS.total : b.subtotal ? COLORS.subtotal : delta < 0 ? COLORS.negative : COLORS.positive;
    if (isAnchor) running = b.value;
    else running += b.value;
    return { label: b.label, value: b.value, base, delta, color, isAnchor };
  });
}

function LightTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm shadow-lg">
      <p className="font-semibold text-neutral-900">{d.label}</p>
      <p className="text-neutral-700">
        {d.value > 0 ? "+" : ""}{d.value.toLocaleString()}
      </p>
      <p className="text-xs text-neutral-500 mt-1">Click to inspect the underlying citations</p>
    </div>
  );
}

const fmtValue = (v) => (v > 0 ? `+${v.toLocaleString()}` : v.toLocaleString());

export default function WaterfallChart({ bars, onBarClick, height = 300 }) {
  if (!bars?.length) return null;
  const data = buildSeries(bars);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 24, right: 10, bottom: 60, left: 10 }}>
        <CartesianGrid stroke="#e5e7eb" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: "#4b5563", fontSize: 11 }}
          interval={0}
          angle={-18}
          textAnchor="end"
          height={70}
        />
        <YAxis tick={{ fill: "#4b5563", fontSize: 11 }} width={50} />
        <Tooltip content={<LightTooltip />} cursor={{ fill: "#f1f5f9" }} />
        <Bar dataKey="base" stackId="wf" fill="transparent" isAnimationActive={false} />
        <Bar
          dataKey="delta"
          stackId="wf"
          radius={[3, 3, 0, 0]}
          onClick={(d) => onBarClick?.(d?.label ?? d?.payload?.label)}
          className="cursor-pointer"
        >
          {data.map((d, i) => (
            <Cell key={i} fill={d.color} />
          ))}
          <LabelList dataKey="delta" position="top" fill="#4b5563" fontSize={10} formatter={fmtValue} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
