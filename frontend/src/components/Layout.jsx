import { NavLink, Outlet } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Overview", end: true },
  { to: "/ingest", label: "Ingest" },
  { to: "/review", label: "Review queue" },
  { to: "/policy", label: "Policy" },
];

export default function Layout() {
  return (
    <div className="min-h-screen bg-[#f8fafc] text-neutral-900">
      <header className="border-b border-neutral-200 sticky top-0 bg-white/95 backdrop-blur z-30 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <NavLink to="/" className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-700 text-white font-bold text-sm">
              CW
            </span>
            <span className="font-bold text-lg tracking-tight text-neutral-900">CiteWise</span>
            <span className="hidden sm:inline text-xs text-neutral-500 font-normal">
              medical citation intelligence
            </span>
          </NavLink>
          <nav className="flex gap-1">
            {LINKS.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-teal-50 text-teal-800 border border-teal-200"
                      : "text-neutral-600 hover:text-neutral-900 hover:bg-neutral-100 border border-transparent"
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-6">
        <Outlet />
      </main>
      <footer className="border-t border-neutral-200 mt-12 bg-white">
        <div className="max-w-6xl mx-auto px-4 py-4 text-xs text-neutral-500">
          CiteWise demo — verification layer over open bibliographic data. Hashes prove a report was not
          altered after generation; they do not prove upstream databases are correct.
        </div>
      </footer>
    </div>
  );
}
