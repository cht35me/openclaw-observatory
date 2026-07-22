import { Compass } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <EmptyState icon={Compass} title="Page not found" description="Nothing lives at this address.">
      <Button asChild variant="outline" size="sm">
        <Link to="/">Back to Dashboard</Link>
      </Button>
    </EmptyState>
  );
}
