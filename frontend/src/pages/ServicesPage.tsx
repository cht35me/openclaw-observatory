import { Workflow } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";

/** Placeholder — Services runtime view lands in M004 PR2. */
export function ServicesPage() {
  return (
    <>
      <PageHeader title="Services" description="Backend, collectors, and exporters." />
      <EmptyState
        icon={Workflow}
        title="Services view is on its way"
        description="This page will show every Observatory service — version, uptime, restart count, CPU, RAM, and network throughput. It arrives with Mission M004 PR2."
      />
    </>
  );
}
