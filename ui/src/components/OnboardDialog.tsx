import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  modalContentClass,
  modalDescriptionClass,
  modalTitleClass,
} from "@/components/AppModal";
import { OnboardPage } from "@/pages/OnboardPage";
import { cn } from "@/lib/utils";

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
        className={cn(
          modalContentClass,
          "flex max-h-[min(920px,92dvh)] w-full flex-col sm:max-w-[720px]",
        )}
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
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden p-6 pb-5">
          <DialogHeader className="shrink-0 gap-1.5">
            <DialogTitle className={modalTitleClass}>Welcome</DialogTitle>
            <DialogDescription className={modalDescriptionClass}>
              {addAgentMode
                ? "Connect another live agent. Existing simulator keys are reused."
                : "Same path as wiretap init — simulator, live agent, suite, then optional phone. Keys stay in the local secret store."}
            </DialogDescription>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <OnboardPage
              addAgentMode={addAgentMode}
              compact
              onFinished={(result) => {
                onOpenChange(false);
                onFinished?.(result);
              }}
            />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
