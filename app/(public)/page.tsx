import type { Metadata } from "next";
import Link from "next/link";
import { StudioLanding } from "@/components/landing/studio-landing";
import { loadCatalog } from "@/lib/catalog";
import { getStudioIdFromEnv, loadApprovedViewModel } from "@/lib/studio-loader";
import type { StudioViewModel } from "@/lib/view-model";

function metadataFromStudio(studio: StudioViewModel): Metadata {
  return {
    title: studio.seo.title,
    description: studio.seo.description,
    openGraph: {
      title: studio.seo.title,
      description: studio.seo.description,
      ...(studio.seo.ogImage ? { images: [{ url: studio.seo.ogImage }] } : {}),
    },
  };
}

export async function generateMetadata(): Promise<Metadata> {
  const studioId = getStudioIdFromEnv();
  if (!studioId) {
    return {
      title: "Estúdios em cena — 100 páginas independentes",
      description: "Uma coleção factual de 100 estúdios musicais brasileiros selecionados por score comercial.",
    };
  }
  const studio = await loadApprovedViewModel(studioId);
  return studio ? metadataFromStudio(studio) : { title: "Estúdio não encontrado" };
}

async function CatalogHome() {
  const catalog = await loadCatalog();
  return (
    <main className="catalog-shell">
      <header className="catalog-hero">
        <div className="catalog-mark" aria-hidden>100</div>
        <div className="catalog-intro">
          <p className="catalog-kicker">Arquivo independente · Brasil</p>
          <h1>Estúdios<br />em cena</h1>
          <p className="catalog-lede">
            Cem endereços para gravar, ensaiar e fazer música — cada um com sua própria direção visual, usando apenas dados comerciais confirmados.
          </p>
          <dl className="catalog-metrics">
            <div><dt>Páginas</dt><dd>{catalog.count}</dd></div>
            <div><dt>Elegíveis</dt><dd>{catalog.eligibleCount}</dd></div>
            <div><dt>Score</dt><dd>{catalog.criteria.minScore}–{catalog.criteria.maxScore}</dd></div>
          </dl>
        </div>
      </header>

      <section className="catalog-list" aria-labelledby="catalog-title">
        <div className="catalog-list-head">
          <h2 id="catalog-title">Índice dos estúdios</h2>
          <p>Ordenado por score comercial</p>
        </div>
        <ol>
          {catalog.studios.map((studio, index) => (
            <li key={studio.studioId}>
              <Link href={studio.href} className="catalog-row">
                <span className="catalog-number">{String(index + 1).padStart(3, "0")}</span>
                <span className="catalog-name">{studio.name}</span>
                <span className="catalog-place">{[studio.city, studio.state].filter(Boolean).join(" · ")}</span>
                <span className="catalog-score">{studio.score.toFixed(2)}</span>
                <span className="catalog-arrow" aria-hidden>↗</span>
              </Link>
            </li>
          ))}
        </ol>
      </section>
      <footer className="catalog-footer">
        <p>Dados públicos · conteúdo sem alegações não verificadas</p>
        <p>Atualizado em {new Intl.DateTimeFormat("pt-BR", { dateStyle: "long", timeZone: "America/Sao_Paulo" }).format(new Date(catalog.generatedAt))}</p>
      </footer>
    </main>
  );
}

export default async function PublicHomePage() {
  const studioId = getStudioIdFromEnv();
  if (!studioId) return <CatalogHome />;
  const studio = await loadApprovedViewModel(studioId);
  if (!studio) {
    return <main className="catalog-error"><h1>Estúdio não encontrado</h1><p>O snapshot aprovado de <code>{studioId}</code> não está disponível.</p></main>;
  }
  return <StudioLanding studio={studio} />;
}
