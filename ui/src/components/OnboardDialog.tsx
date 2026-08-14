import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { OnboardPage } from "@/pages/OnboardPage";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Skip simulator; connect another agent. */
  addAgentMode?: boolean;
  /** First-run: cannot dismiss until finished. */
  required?: boolean;
  onFinished?: (result: { suiteName: string | null }) => void;
};

/** First-run / re-run setup over the dashboard with a blurred backdrop. */
export function OnboardDialog({
  open,
  onOpenChange,
  addAgentMode = false,
  required = false,
  onFinished,
}: Props) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && required) return;
        onOpenChange(next);
      }}
    >
      <DialogContent
        showCloseButton={!required}
        overlayClassName="bg-black/35 supports-backdrop-filter:backdrop-blur-md"
        className="flex max-h-[min(920px,92dvh)] w-full flex-col gap-0 overflow-hidden rounded-[18px] border-border bg-card p-0 text-sm shadow-[0_30px_80px_-20px_rgba(41,41,39,0.28)] sm:max-w-[720px]"
        onPointerDownOutside={(e) => {
          if (required) e.preventDefault();
        }}
        onEscapeKeyDown={(e) => {
          if (required) e.preventDefault();
        }}
        onInteractOutside={(e) => {
          if (required) e.preventDefault();
        }}
      >
        <div className="flex shrink-0 items-center gap-3 border-b border-border px-6 py-4">
          <div className="min-w-0">
            <DialogTitle className="sr-only">Wiretap</DialogTitle>
            <img
              src="/wiretap-wordmark.png"
              alt=""
              className="h-8 w-auto max-w-full select-none"
              draggable={false}
            />
            {!addAgentMode ? (
              <DialogDescription className="mt-1 text-xs text-muted-foreground">
                First-time setup
              </DialogDescription>
            ) : (
              <DialogDescription className="sr-only">
                Setup
              </DialogDescription>
            )}
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <OnboardPage
            addAgentMode={addAgentMode}
            compact
            onFinished={(result) => {
              onOpenChange(false);
              onFinished?.(result);
            }}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
