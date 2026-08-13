import Link from "next/link";
import { notFound } from "next/navigation";
import { StudioActions } from "@/components/dashboard/studio-actions";
import { JsonStateRepository } from "@/lib/repositories/state-repository";
import { JsonStudioRepository } from "@/lib/repositories/studio-repository";

export default async function StudioDashboardPage({ params }: PageProps<"/dashboard/studios/[studioId]">) {
  const { studioId } = await params;
  const studios = new JsonStudioRepository();
  const state = new JsonStateRepository(undefined, studios);
  const [studio, dossier, generated, approved, deployment, pipeline] = await Promise.all([
    studios.getStudio(studioId), studios.getDossier(studioId), studios.getGenerated(studioId),
    studios.getApproved(studioId), studios.getDeployment(studioId), state.getItem(studioId),
  ]);
  if (!studio || !generated) notFound();

  return (
    <main className="min-h-screen bg-[#11110f] px-5 py-8 text-[#f0eadf] sm:px-9 lg:px-14">
      <div className="mx-auto max-w-7xl">
        <nav className="flex flex-wrap justify-between gap-4 font-mono text-[.68rem] uppercase tracking-[.16em]">
          <Link href="/dashboard" className="text-[#d7ff3f]">← Todos os estúdios</Link>
          <Link href={`/studios/${studioId}`} target="_blank">Abrir página ↗</Link>
        </nav>
        <header className="mt-12 grid gap-8 border-b border-[#f0eadf]/20 pb-10 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-end">
          <div>
            <p className="font-mono text-[.65rem] uppercase tracking-[.24em] text-[#f0eadf]/50">{studio.location.city} / score {studio.commercialScore?.toFixed(2)}</p>
            <h1 className="mt-4 max-w-4xl text-5xl font-semibold tracking-[-.06em] sm:text-7xl">{studio.name}</h1>
          </div>
          <dl className="grid grid-cols-2 gap-y-2 font-mono text-[.68rem] uppercase tracking-[.12em]">
            <dt className="text-[#f0eadf]/45">Status</dt><dd className="text-right text-[#d7ff3f]">{pipeline?.status ?? "—"}</dd>
            <dt className="text-[#f0eadf]/45">Template</dt><dd className="text-right">{generated.templateId}</dd>
            <dt className="text-[#f0eadf]/45">Geração</dt><dd className="truncate text-right">{generated.generationId.slice(-10)}</dd>
          </dl>
        </header>

        <div className="grid gap-8 py-10 lg:grid-cols-[minmax(0,1.6fr)_minmax(19rem,.7fr)]">
          <section>
            <div className="mb-4 flex items-center justify-between gap-4">
              <h2 className="font-mono text-xs uppercase tracking-[.2em]">Prévia aprovada</h2>
              <Link href={`/preview/${studioId}`} target="_blank" className="text-xs underline underline-offset-4">Abrir rascunho</Link>
            </div>
            <div className="overflow-hidden rounded-sm border border-[#f0eadf]/20 bg-white">
              <iframe title={`Prévia de ${studio.name}`} src={`/preview/${studioId}`} className="h-[48rem] w-full" loading="lazy" />
            </div>
          </section>

          <aside className="space-y-8">
            <StudioActions studioId={studioId} templateId={generated.templateId} status={pipeline?.status ?? "unknown"} hasAi={Boolean(process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN)} hasDeployHook={Boolean(process.env.VERCEL_DEPLOY_HOOK_URL)} />
            <section className="border border-[#f0eadf]/20 p-5">
              <h2 className="font-mono text-xs uppercase tracking-[.2em] text-[#d7ff3f]">Proveniência</h2>
              <dl className="mt-5 grid grid-cols-[7rem_1fr] gap-y-3 text-xs leading-5">
                <dt className="text-[#f0eadf]/45">Fonte</dt><dd>{studio.source.sourceFile}</dd>
                <dt className="text-[#f0eadf]/45">Evidências</dt><dd>{generated.factualClaims.length}</dd>
                <dt className="text-[#f0eadf]/45">Mídias</dt><dd>{dossier?.media.selected.length ?? 0}</dd>
                <dt className="text-[#f0eadf]/45">Aprovação</dt><dd>{approved ? `${approved.approvedBy} · ${approved.approvedAt.slice(0, 10)}` : "pendente"}</dd>
                <dt className="text-[#f0eadf]/45">Deploy</dt><dd>{deployment?.status ?? "não solicitado"}</dd>
              </dl>
            </section>
          </aside>
        </div>
      </div>
    </main>
  );
}
