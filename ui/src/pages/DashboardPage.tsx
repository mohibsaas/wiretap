import { Link } from "react-router-dom";
import { Activity, Bot, LineChart, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const cards = [
  {
    eyebrow: "Runs",
    title: "Runs this week",
    hint: "How many calls you put on the record.",
    icon: Activity,
    to: "/evaluations",
  },
  {
    eyebrow: "Verdict",
    title: "Clean vs flagged",
    hint: "The split across your latest suite.",
    icon: LineChart,
    to: "/evaluations",
  },
  {
    eyebrow: "Agents",
    title: "Agents under tap",
    hint: "The voice agents you're watching.",
    icon: Bot,
    to: "/agents",
  },
  {
    eyebrow: "Spend",
    title: "Sim spend",
    hint: "What your runs cost across the workspace.",
    icon: Wallet,
    to: "/settings",
  },
];

export function DashboardPage() {
  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start justify-between gap-5">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-baseline gap-2.5">
            <h1 className="text-[22px] font-semibold tracking-[-0.005em] text-foreground">
              Dashboard
            </h1>
            <span className="text-[13px] font-medium text-[var(--wt-text-muted)]">
              1 dashboard
            </span>
          </div>
          <p className="max-w-xl text-[13.5px] leading-relaxed text-muted-foreground text-pretty">
            What the taps see, at a glance.
          </p>
        </div>
        <Button asChild>
          <Link to="/suites">Open suites</Link>
        </Button>
      </header>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {cards.map((card) => (
          <Card key={card.title} className="min-h-[220px] ring-border">
            <CardHeader>
              <div className="text-[11px] font-semibold tracking-[0.06em] text-[var(--wt-text-muted)] uppercase">
                {card.eyebrow}
              </div>
              <CardTitle>{card.title}</CardTitle>
              <CardDescription>{card.hint}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col items-center justify-center gap-2 py-4 text-[var(--wt-text-muted)]">
              <card.icon className="size-[22px]" />
              <div className="text-sm font-medium text-muted-foreground">No data</div>
              <div className="text-xs text-[var(--wt-text-muted)]">
                Nothing on the record yet
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
