import { Button } from "@/components/ui/button";
import { AppModal } from "@/components/AppModal";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Destructive styling for irreversible actions (default). */
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
};

/** In-app confirm — replaces `window.confirm` for deletes and similar. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  destructive = true,
  busy = false,
  onConfirm,
}: Props) {
  return (
    <AppModal
      open={open}
      onOpenChange={(next) => {
        if (busy) return;
        onOpenChange(next);
      }}
      title={title}
      description={description}
      maxWidthClass="sm:max-w-[420px]"
      showCloseButton={false}
      compactBody
      footer={
        <>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            onClick={() => void onConfirm()}
            disabled={busy}
          >
            {busy ? "Working…" : confirmLabel}
          </Button>
        </>
      }
    />
  );
}
