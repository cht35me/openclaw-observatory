import { PageHeader } from "@/components/PageHeader";
import { ServicesView } from "@/features/services/ServicesView";

/** Services runtime view (mission §5): backend, collectors, exporters. */
export function ServicesPage() {
  return (
    <>
      <PageHeader title="Services" description="Backend, collectors, and exporters." />
      <ServicesView />
    </>
  );
}
