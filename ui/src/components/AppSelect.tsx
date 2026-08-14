import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

export type AppSelectOption = {
  value: string;
  label: string;
  disabled?: boolean;
};

type Props = {
  id?: string;
  value: string;
  onValueChange: (value: string) => void;
  options: AppSelectOption[];
  placeholder?: string;
  /** Extra classes on the trigger (full-width form control by default). */
  triggerClassName?: string;
  contentClassName?: string;
  mono?: boolean;
  disabled?: boolean;
  "aria-label"?: string;
};

/**
 * Wiretap form select — same shadcn Select used on Simulations filters /
 * Settings, with consistent height, radius, and popper menu.
 */
export function AppSelect({
  id,
  value,
  onValueChange,
  options,
  placeholder = "Select…",
  triggerClassName,
  contentClassName,
  mono = false,
  disabled = false,
  "aria-label": ariaLabel,
}: Props) {
  const safeValue =
    value && options.some((o) => o.value === value)
      ? value
      : options.find((o) => !o.disabled)?.value;

  return (
    <Select
      value={safeValue}
      onValueChange={onValueChange}
      disabled={disabled || options.length === 0}
    >
      <SelectTrigger
        id={id}
        aria-label={ariaLabel}
        className={cn(
          "h-10 w-full min-w-0 rounded-[10px] border-input bg-card font-sans text-[13px]",
          mono && "font-mono",
          triggerClassName,
        )}
      >
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent
        position="popper"
        className={cn(
          "max-h-72 min-w-[var(--radix-select-trigger-width)] p-1.5 font-sans text-[13px]",
          mono && "font-mono",
          contentClassName,
        )}
      >
        {options.map((o) => (
          <SelectItem
            key={o.value}
            value={o.value}
            disabled={o.disabled}
            className={cn(
              "rounded-md py-1.5 pr-8 pl-2 font-sans text-[13px]",
              mono && "font-mono",
            )}
          >
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
