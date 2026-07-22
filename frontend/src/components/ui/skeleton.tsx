// shadcn/ui skeleton (vendored source). The only "animation" in the console
// is this unobtrusive loading pulse — status indicators never animate.
import { cn } from "@/utils/cn";

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}

export { Skeleton };
