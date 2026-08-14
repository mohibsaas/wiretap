import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/** Shared chrome for Connect / New run / New suite / Confirm dialogs. */
export const modalContentClass =
  "gap-0 overflow-hidden rounded-[18px] border-border bg-card p-0 text-sm shadow-[0_30px_80px_-20px_rgba(41,41,39,0.28)]";

export const modalBodyClass = "flex min-w-0 flex-col gap-4 p-6 pb-4";

export const modalFieldsClass = "flex min-w-0 flex-col gap-3.5";

export const modalFieldClass = "flex min-w-0 flex-col gap-1.5";

export const modalTitleClass =
  "text-base font-semibold tracking-[-0.01em] text-foreground";

export const modalDescriptionClass =
  "text-[13px] leading-relaxed text-muted-foreground text-pretty";

export const modalFooterClass = "gap-2 rounded-b-[18px] sm:justify-end";

export const modalLabelClass = "text-[13px] font-medium text-foreground";

export const modalInputClass = "h-10 rounded-[10px] font-sans text-[13px]";

export const modalHintClass = "text-xs leading-relaxed text-muted-foreground";

type AppModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children?: ReactNode;
  footer?: ReactNode;
  /** Tailwind max-width utility, e.g. sm:max-w-[480px] */
  maxWidthClass?: string;
  showCloseButton?: boolean;
  /** Tighter body when there are no form fields (confirm). */
  compactBody?: boolean;
  bodyClassName?: string;
};

/**
 * Standard Wiretap modal: rounded card, padded header/body, muted footer bar.
 * Use for form and confirm dialogs so spacing/type stay aligned.
 */
export function AppModal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  maxWidthClass = "sm:max-w-[480px]",
  showCloseButton = true,
  compactBody = false,
  bodyClassName,
}: AppModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={showCloseButton}
        className={cn(modalContentClass, maxWidthClass)}
      >
        <div
          className={cn(
            compactBody
              ? "flex min-w-0 flex-col gap-2 p-6 pb-4"
              : modalBodyClass,
            bodyClassName,
          )}
        >
          <DialogHeader className="gap-1.5">
            <DialogTitle className={modalTitleClass}>{title}</DialogTitle>
            {description ? (
              <DialogDescription className={modalDescriptionClass}>
                {description}
              </DialogDescription>
            ) : null}
          </DialogHeader>
          {children}
        </div>
        {footer ? (
          <DialogFooter className={modalFooterClass}>{footer}</DialogFooter>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
