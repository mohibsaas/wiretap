import { NavLink, Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";

const links = [
  { to: "/agents", label: "Agents" },
  { to: "/suites", label: "Test suites" },
  { to: "/evaluations", label: "Evaluations" },
];

export function AppShell() {
  return (
    <div className="flex min-h-screen bg-background">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-card">
        <div className="border-b border-border px-4 py-4">
          <div className="text-lg font-semibold tracking-tight">wiretap</div>
          <div className="text-xs text-muted-foreground">local eval</div>
        </div>
        <nav className="flex flex-col gap-0.5 p-2">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground",
                  isActive && "bg-muted font-medium text-foreground",
                )
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto border-t border-border p-3 text-[11px] leading-relaxed text-muted-foreground">
          CLI still works: <span className="font-mono">wiretap simulate</span>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-8 py-8">
        <Outlet />
      </main>
    </div>
  );
}
