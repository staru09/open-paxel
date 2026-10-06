import { Link, Outlet, useLocation } from "react-router-dom";
import { DEMO } from "../lib/api";
import { JobProgressBanner } from "./JobProgressBanner";

const links = [
  { to: "/", label: "Profile" },
  { to: "/sessions", label: "Sessions" },
  ...(DEMO ? [] : [{ to: "/uploads", label: "Uploads" }]),
];

export function Layout() {
  const { pathname } = useLocation();

  return (
    <div className="min-h-screen bg-cream">
      <header className="border-b-2 border-ink bg-card px-6 py-4">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
          <div>
            <h1 className="font-display text-2xl font-bold tracking-tight">Open-Paxel</h1>
            <p className="text-sm opacity-70">How do you build with AI?</p>
          </div>
          <nav className="flex gap-2">
            {links.map(({ to, label }) => (
              <Link
                key={to}
                to={to}
                className={`btn-brutal rounded-none px-4 py-2 text-sm font-semibold ${
                  pathname === to || (to !== "/" && pathname.startsWith(to))
                    ? "bg-warm-yellow"
                    : "bg-cream-dark"
                }`}
              >
                {label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      {DEMO && (
        <div className="border-b-2 border-ink bg-warm-yellow px-6 py-2 text-center text-sm">
          Demo profile built from a real, redacted Claude Code session.{" "}
          <a className="font-semibold underline" href="https://github.com/staru09/open-paxel">
            Run Open-Paxel on your own sessions
          </a>
        </div>
      )}
      <JobProgressBanner />
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
