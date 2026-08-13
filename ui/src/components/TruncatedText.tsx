import { useEffect, useRef, useState } from "react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type TruncatedTextProps = {
  text: string;
  className?: string;
  /** Tooltip content override (defaults to `text`). */
  tooltip?: string;
  /** Multi-line clamp; omit for single-line truncate. */
  lines?: number;
  as?: "span" | "p" | "div";
};

/**
 * Truncates overflowing text and shows a shadcn tooltip with the full value
 * when (and only when) the content is actually clipped.
 */
export function TruncatedText({
  text,
  className,
  tooltip,
  lines,
  as: Comp = "span",
}: TruncatedTextProps) {
  const ref = useRef<HTMLElement | null>(null);
  const [truncated, setTruncated] = useState(false);
  const tip = tooltip ?? text;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const check = () => {
      const overflowX = el.scrollWidth > el.clientWidth + 1;
      const overflowY = el.scrollHeight > el.clientHeight + 1;
      setTruncated(overflowX || overflowY);
    };

    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, [text, lines, className]);

  const node = (
    <Comp
      ref={ref as never}
      className={cn(
        "min-w-0",
        lines && lines > 1 ? "break-words" : "block truncate",
        className,
      )}
      style={
        lines && lines > 1
          ? {
              display: "-webkit-box",
              WebkitLineClamp: lines,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }
          : undefined
      }
    >
      {text}
    </Comp>
  );

  if (!truncated || !tip) return node;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{node}</TooltipTrigger>
      <TooltipContent
        sideOffset={6}
        className="max-w-sm whitespace-pre-wrap break-all text-left"
      >
        {tip}
      </TooltipContent>
    </Tooltip>
  );
}
