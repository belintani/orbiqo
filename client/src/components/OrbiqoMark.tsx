import { cn } from "@/lib/utils";

export function OrbiqoMark({ className = "" }: { className?: string }) {
  return (
    <span className={cn("orbiqo-mark", className)} aria-hidden="true">
      <span className="orbiqo-mark__ring orbiqo-mark__ring--outer" />
      <span className="orbiqo-mark__ring orbiqo-mark__ring--middle" />
      <span className="orbiqo-mark__ring orbiqo-mark__ring--inner" />
      <span className="orbiqo-mark__core">O</span>
    </span>
  );
}
