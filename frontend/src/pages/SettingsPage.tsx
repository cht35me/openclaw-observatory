import { PageHeader } from "@/components/PageHeader";
import { ApiKeyForm } from "@/features/settings/ApiKeyForm";

export function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Connection to the Observatory backend." />
      <ApiKeyForm />
    </>
  );
}
