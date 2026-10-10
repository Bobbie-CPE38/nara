import { CaseView } from "@/components/case/CaseView";

export default async function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // Keyed by case, so another ID starts empty instead of showing the previous case for a frame.
  return <CaseView key={id} caseId={id} />;
}
