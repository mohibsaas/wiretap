import { useEffect, useMemo, useState, type ComponentType } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Bot,
  CheckCircle2,
  ChevronUp,
  Circle,
  FileText,
  LayoutGrid,
  Play,
  Settings,
  Shapes,
  SquareCheckBig,
} from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { client, type OnboardStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

type NavItem = {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  end?: boolean;
};

const monitor: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutGrid, end: true },
  { to: "/reports", label: "Reports", icon: FileText },
];

const evaluate: NavItem[] = [
  { to: "/suites", label: "Test Suites", icon: SquareCheckBig },
  { to: "/categories", label: "Test Categories", icon: Shapes },
  { to: "/evaluations", label: "Simulations", icon: Play },
  { to: "/agents", label: "Agents", icon: Bot },
];

const configure: NavItem[] = [
  { to: "/settings", label: "Settings", icon: Settings },
];

function NavSection({ title, items }: { title: string; items: NavItem[] }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="px-3 pb-1.5 text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
        {title}
      </div>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            cn(
              "relative flex items-center gap-2.5 rounded-[10px] px-3 py-2 text-[13.5px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
              isActive &&
                "bg-sidebar-accent font-medium text-foreground before:absolute before:top-1.5 before:bottom-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-primary",
            )
          }
        >
          <item.icon className="size-[17px] shrink-0" />
          <span>{item.label}</span>
        </NavLink>
      ))}
    </div>
  );
}

export function AppShell() {
  const location = useLocation();
  const [status, setStatus] = useState<OnboardStatus | null>(null);
  const [evalCount, setEvalCount] = useState(0);
  const [checklistOpen, setChecklistOpen] = useState(true);

  const isTranscriptPage = /\/evaluations\/[^/]+\/scenarios\/[^/]+/.test(
    location.pathname,
  );

  useEffect(() => {
    void client.onboardStatus().then(setStatus).catch(() => setStatus(null));
    void client
      .evaluations(5)
      .then((rows) => setEvalCount(rows.length))
      .catch(() => setEvalCount(0));
  }, [location.pathname]);

  /** Mirrors onboarding steps (Wiretap.dc.html setup checklist). */
  const checklist = useMemo(() => {
    const callerReady = Boolean(
      status?.caller_configured || status?.has_llm_key || status?.caller,
    );
    const agentReady = Boolean(
      status?.agent_id ||
        status?.has_platform_key ||
        (status?.platform && status.platform !== "custom"),
    );
    const suiteReady = (status?.suite_count ?? 0) > 0;
    const simulated = evalCount > 0;

    const items = [
      {
        id: "caller",
        label: "Setup Evaluation Agent",
        done: callerReady,
        to: "/settings",
      },
      {
        id: "agent",
        label: "Connect Target Agent",
        done: agentReady,
        to: "/agents",
      },
      {
        id: "suite",
        label: "Generate Test Suite",
        done: suiteReady,
        to: "/suites",
      },
      {
        id: "simulate",
        label: "Run the Simulation",
        done: simulated,
        to: "/evaluations",
      },
    ];
    const done = items.filter((i) => i.done).length;
    return {
      items,
      done,
      total: items.length,
      pct: (done / items.length) * 100,
    };
  }, [status, evalCount]);

  const showChecklist = checklist.done < checklist.total;

  return (
    <div className="flex h-dvh overflow-hidden bg-sidebar">
      <aside className="flex h-full w-64 shrink-0 flex-col px-3.5 pt-3.5 pb-2.5">
        <div className="flex items-center rounded-xl px-2 py-2.5">
          <img
            src="/wiretap-wordmark.png"
            alt="Wiretap"
            className="h-7 w-auto max-w-full select-none"
            draggable={false}
          />
        </div>

        <ScrollArea className="min-h-0 flex-1 py-3.5">
          <div className="flex flex-col gap-3.5 pr-1">
            <NavSection title="Monitor" items={monitor} />
            <NavSection title="Evaluate" items={evaluate} />
            <NavSection title="Configure" items={configure} />
          </div>
        </ScrollArea>

        {showChecklist && (
          <Collapsible
            open={checklistOpen}
            onOpenChange={setChecklistOpen}
            className="mb-2.5 rounded-[14px] border border-border bg-card px-3.5 py-3"
          >
            <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 text-left">
              <div className="text-[13.5px] font-semibold text-foreground">
                Set up your project
              </div>
              <ChevronUp
                className={cn(
                  "size-3.5 text-muted-foreground transition-transform",
                  !checklistOpen && "rotate-180",
                )}
              />
            </CollapsibleTrigger>
            <div className="mt-1.5 text-xs text-muted-foreground">
              {checklist.done} of {checklist.total} done
            </div>
            <Progress value={checklist.pct} className="mt-2.5 h-[3px]" />
            <CollapsibleContent className="mt-3 flex flex-col gap-2.5">
              {checklist.items.map((item) => (
                <Link
                  key={item.id}
                  to={item.to}
                  className="flex items-center gap-2.5 rounded-md py-0.5 transition-colors hover:bg-muted/60"
                >
                  {item.done ? (
                    <CheckCircle2 className="size-[15px] shrink-0 text-primary" />
                  ) : (
                    <Circle className="size-[15px] shrink-0 text-[var(--wt-text-muted)]" />
                  )}
                  <span
                    className={cn(
                      "min-w-0 flex-1 text-[12.5px] leading-snug",
                      item.done
                        ? "text-muted-foreground line-through"
                        : "text-foreground",
                    )}
                  >
                    {item.label}
                  </span>
                </Link>
              ))}
            </CollapsibleContent>
          </Collapsible>
        )}

        <Separator className="mb-2" />
        <div className="flex items-center gap-3 rounded-[10px] px-2.5 py-2.5">
          <Avatar size="default" className="size-9">
            <AvatarFallback className="bg-primary text-[11px] font-semibold tracking-wide text-primary-foreground">
              WT
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-semibold text-foreground">
              Local user
            </div>
            <div className="truncate text-[11.5px] text-muted-foreground">
              wiretap simulate
            </div>
          </div>
        </div>
      </aside>

      <div className="m-2 ml-0 flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-[0_12px_32px_-12px_rgba(41,41,39,0.20)]">
        <main className="min-h-0 flex-1 overflow-auto px-8 py-6">
          <div
            className={cn(
              "w-full",
              // Transcript / scenario detail uses the full canvas width.
              !isTranscriptPage && "mx-auto max-w-[1120px]",
            )}
          >
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
