import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

type Option = { value: string; label: string };

type Props = {
  icon?: ReactNode;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Option[];
  /** Value that means “no filter” — highlights the trigger when different. */
  allValue?: string;
  align?: "start" | "center" | "end";
};

/** Chip-style filter dropdown used on Simulations (and elsewhere). */
export function FilterMenu({
  icon,
  label,
  value,
  onChange,
  options,
  allValue = "all",
  align = "start",
}: Props) {
  const selected = options.find((o) => o.value === value)?.label;
  const active = value !== allValue;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn(
            "h-9 gap-1.5 rounded-[10px]",
            active && "border-primary bg-accent text-accent-foreground",
          )}
        >
          {icon}
          <span>{label}</span>
          {active && (
            <span className="max-w-[90px] truncate text-muted-foreground">
              {selected}
            </span>
          )}
          <ChevronDown data-icon="inline-end" className="opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} className="min-w-48 p-1.5">
        <DropdownMenuLabel className="px-2 py-1.5">{label}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup value={value} onValueChange={onChange}>
          {options.map((o) => (
            <DropdownMenuRadioItem
              key={o.value}
              value={o.value}
              className="rounded-md py-1.5 pr-8 pl-2"
            >
              {o.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
