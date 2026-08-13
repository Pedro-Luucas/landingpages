import Link from "next/link";
import { loadCatalog } from "@/lib/catalog";
import { JsonStateRepository } from "@/lib/repositories/state-repository";

export default async function DashboardPage() {
  const [catalog, pipeline] = await Promise.all([
    loadCatalog(),
    new JsonStateRepository().getPipeline(),
  ]);
  const statusById = new Map(pipeline.items.map((item) => [item.studioId, item.status]));
  const counts = pipeline.items.reduce<Record<string, number>>((acc, item) => {
    acc[item.status] = (acc[item.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <main className="min-h-screen bg-[#11110f] px-5 py-8 text-[#f0eadf] sm:px-9 lg:px-14">
      <header className="mx-auto flex max-w-7xl flex-col gap-8 border-b border-[#f0eadf]/20 pb-10 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="font-mono text-[.66rem] uppercase tracking-[.28em] text-[#d7ff3f]">Operação / páginas aprovadas</p>
          <h1 className="mt-4 text-5xl font-semibold tracking-[-.065em] sm:text-7xl">100 estúdios</h1>
        </div>
        <dl className="grid grid-cols-2 gap-x-10 gap-y-2 font-mono text-xs uppercase tracking-[.12em] text-[#f0eadf]/60">
          <dt>Aprovadas</dt><dd className="text-right text-[#f0eadf]">{counts.approved ?? 0}</dd>
          <dt>Publicadas</dt><dd className="text-right text-[#f0eadf]">{counts.deployed ?? 0}</dd>
          <dt>Em revisão</dt><dd className="text-right text-[#f0eadf]">{counts.ready_for_review ?? 0}</dd>
          <dt>Elegíveis</dt><dd className="text-right text-[#f0eadf]">{catalog.eligibleCount}</dd>
        </dl>
      </header>

      <section className="mx-auto max-w-7xl py-10" aria-labelledby="studio-list-title">
        <div className="mb-5 flex items-center justify-between gap-4">
          <h2 id="studio-list-title" className="font-mono text-xs uppercase tracking-[.22em]">Fila editorial</h2>
          <Link href="/" className="font-mono text-xs text-[#d7ff3f] underline underline-offset-4">Ver coleção pública</Link>
        </div>
        <ol className="border-t border-[#f0eadf]/25">
          {catalog.studios.map((studio, index) => (
            <li key={studio.studioId}>
              <Link href={`/dashboard/studios/${studio.studioId}`} className="group grid grid-cols-[2.5rem_minmax(0,1fr)_4rem] items-baseline gap-3 border-b border-[#f0eadf]/15 py-4 transition-colors hover:bg-[#f0eadf]/[.04] sm:grid-cols-[3rem_minmax(0,2fr)_minmax(8rem,1fr)_6rem_7rem]">
                <span className="font-mono text-[.62rem] text-[#f0eadf]/45">{String(index + 1).padStart(3, "0")}</span>
                <strong className="truncate text-lg font-medium tracking-[-.025em]">{studio.name}</strong>
                <span className="hidden truncate text-sm text-[#f0eadf]/50 sm:block">{[studio.city, studio.state].filter(Boolean).join(" / ")}</span>
                <span className="text-right font-mono text-xs">{studio.score.toFixed(2)}</span>
                <span className="hidden text-right font-mono text-[.6rem] uppercase tracking-[.12em] text-[#d7ff3f] sm:block">{statusById.get(studio.studioId) ?? "—"}</span>
              </Link>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
