import type { LandingTemplateProps } from "@/lib/view-model";
import { FOCUS_RING } from "../_shared/focus";
import { MapLink } from "../_shared/MapLink";
import { LandingSection } from "../_shared/LandingSection";
import { StudioFrame } from "../_shared/StudioFrame";
import { StudioImg } from "../_shared/StudioImg";
import {
  heroCtaHref,
  showAbout,
  showContact,
  showEquipment,
  showGallery,
  showHours,
  showMap,
  showPricing,
  showReviews,
} from "../_shared/visibility";
import "./editorial.css";

export function EditorialTemplate({ studio }: LandingTemplateProps) {
  const ctaHref = heroCtaHref(studio);
  const leadImage = studio.hero.image;
  const restGallery = showGallery(studio)
    ? studio.gallery.filter((image) => image.src !== leadImage?.src)
    : [];

  return (
    <StudioFrame studio={studio} className="editorial-root">
      <article className="relative mx-auto w-full max-w-5xl px-4 py-10 sm:px-8 sm:py-16">
        <header className="editorial-hairline mb-10 flex items-baseline justify-between gap-4 border-b pb-4">
          {studio.hero.eyebrow ? (
            <p className={`editorial-kicker text-[0.68rem] uppercase text-[var(--studio-muted)] ${studio.fontHeadingClass}`}>
              {studio.hero.eyebrow}
            </p>
          ) : (
            <span />
          )}
          <p className="text-[0.68rem] uppercase tracking-[0.18em] text-[var(--studio-muted)]">
            Estúdio
          </p>
        </header>

        <main id="conteudo">
          <div className="grid gap-10 md:grid-cols-[minmax(0,1.4fr)_minmax(0,0.9fr)] md:items-end">
            <div className="min-w-0">
              <h1
                className={`${studio.fontHeadingClass} text-balance text-[clamp(2.4rem,9vw,5.4rem)] leading-[0.92] tracking-[-0.03em]`}
              >
                {studio.hero.title}
              </h1>
            </div>
            <div className="min-w-0 max-w-[var(--editorial-measure)] md:justify-self-end">
              {studio.hero.subtitle ? (
                <p className="text-[1.05rem] leading-8 text-[var(--studio-muted)]">
                  {studio.hero.subtitle}
                </p>
              ) : null}
              {studio.hero.primaryCta && ctaHref ? (
                <a
                  href={ctaHref}
                  className={`mt-6 inline-block border-b border-[var(--studio-primary)] pb-0.5 text-sm tracking-wide text-[var(--studio-primary)] ${FOCUS_RING}`}
                >
                  {studio.hero.primaryCta}
                </a>
              ) : null}
            </div>
          </div>

          {leadImage ? (
            <figure className="mt-12">
              <StudioImg
                image={leadImage}
                priority
                className="h-auto w-full max-w-full"
                sizes="(max-width: 768px) 100vw, 64rem"
              />
              <figcaption className="mt-3 max-w-[var(--editorial-measure)] text-sm italic text-[var(--studio-muted)]">
                {leadImage.alt}
              </figcaption>
            </figure>
          ) : null}

          {showAbout(studio) && studio.about ? (
            <LandingSection
              id="sobre"
              labelledBy="editorial-sobre"
              className="mx-auto mt-16 max-w-[var(--editorial-measure)]"
            >
              <h2
                id="editorial-sobre"
                className={`${studio.fontHeadingClass} mb-6 text-3xl leading-tight sm:text-4xl`}
              >
                {studio.about.title}
              </h2>
              <p className="editorial-drop text-[1.08rem] leading-8 [text-wrap:pretty]">
                {studio.about.body}
              </p>
            </LandingSection>
          ) : null}

          {restGallery.length > 0 ? (
            <LandingSection id="galeria" labelledBy="editorial-galeria" className="mt-20">
              <h2
                id="editorial-galeria"
                className={`${studio.fontHeadingClass} mb-8 text-2xl`}
              >
                Galeria
              </h2>
              <div className="grid grid-cols-1 gap-8 sm:grid-cols-2">
                {restGallery.map((image, index) => (
                  <figure key={`${image.src}-${index}`} className="min-w-0">
                    <StudioImg
                      image={image}
                      className="h-auto w-full max-w-full"
                      sizes="(max-width: 640px) 100vw, 28rem"
                    />
                    <figcaption className="mt-2 text-xs tracking-wide text-[var(--studio-muted)]">
                      Fig. {String(index + 1).padStart(2, "0")} — {image.alt}
                    </figcaption>
                  </figure>
                ))}
              </div>
            </LandingSection>
          ) : null}

          {showReviews(studio) && studio.reviews ? (
            <LandingSection id="avaliacoes" labelledBy="editorial-avaliacoes" className="mt-20">
              <h2
                id="editorial-avaliacoes"
                className={`${studio.fontHeadingClass} mb-2 text-2xl`}
              >
                {studio.reviews.title}
              </h2>
              {typeof studio.reviews.rating === "number" ||
              typeof studio.reviews.count === "number" ? (
                <p className="mb-10 text-sm text-[var(--studio-muted)]">
                  {typeof studio.reviews.rating === "number"
                    ? studio.reviews.rating.toLocaleString("pt-BR", {
                        minimumFractionDigits: 1,
                        maximumFractionDigits: 1,
                      })
                    : null}
                  {typeof studio.reviews.rating === "number" &&
                  typeof studio.reviews.count === "number"
                    ? " · "
                    : null}
                  {typeof studio.reviews.count === "number"
                    ? `${studio.reviews.count} avaliações`
                    : null}
                </p>
              ) : null}
              <div className="grid gap-12">
                {studio.reviews.excerpts?.map((excerpt) => (
                  <blockquote
                    key={excerpt}
                    className={`editorial-quote pl-2 sm:pl-8 ${studio.fontHeadingClass}`}
                  >
                    <p className="text-pretty text-[clamp(1.4rem,3.4vw,2.15rem)] leading-snug">
                      {excerpt}
                    </p>
                  </blockquote>
                ))}
              </div>
            </LandingSection>
          ) : null}

          {showEquipment(studio) && studio.equipment ? (
            <LandingSection
              id="equipamentos"
              labelledBy="editorial-equipamentos"
              className="mx-auto mt-20 max-w-[var(--editorial-measure)]"
            >
              <h2
                id="editorial-equipamentos"
                className={`${studio.fontHeadingClass} mb-4 text-2xl`}
              >
                {studio.equipment.title}
              </h2>
              {studio.equipment.intro ? (
                <p className="mb-6 text-[var(--studio-muted)]">{studio.equipment.intro}</p>
              ) : null}
              <ul className="list-disc space-y-2 pl-5 marker:text-[var(--studio-primary)]">
                {studio.equipment.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </LandingSection>
          ) : null}

          <div className="mt-20 grid gap-12 md:grid-cols-2">
            {showPricing(studio) && studio.pricing ? (
              <LandingSection id="precos" labelledBy="editorial-precos" className="min-w-0">
                <h2
                  id="editorial-precos"
                  className={`${studio.fontHeadingClass} mb-6 text-2xl`}
                >
                  {studio.pricing.title}
                </h2>
                <dl className="editorial-rows">
                  {studio.pricing.items.map((item) => (
                    <div
                      key={`${item.label}-${item.value}`}
                      className="flex flex-wrap items-baseline justify-between gap-2 py-3"
                    >
                      <dt>{item.label}</dt>
                      <dd className={`${studio.fontHeadingClass} text-lg`}>{item.value}</dd>
                      {item.note ? (
                        <p className="w-full text-sm text-[var(--studio-muted)]">{item.note}</p>
                      ) : null}
                    </div>
                  ))}
                </dl>
              </LandingSection>
            ) : null}

            {showHours(studio) && studio.hours ? (
              <LandingSection id="horarios" labelledBy="editorial-horarios" className="min-w-0">
                <h2
                  id="editorial-horarios"
                  className={`${studio.fontHeadingClass} mb-6 text-2xl`}
                >
                  {studio.hours.title}
                </h2>
                <dl className="space-y-2 text-sm">
                  {studio.hours.items.map((item) => (
                    <div
                      key={`${item.day}-${item.value}`}
                      className="flex justify-between gap-4"
                    >
                      <dt className="text-[var(--studio-muted)]">{item.day}</dt>
                      <dd>{item.value}</dd>
                    </div>
                  ))}
                </dl>
              </LandingSection>
            ) : null}
          </div>

          {showContact(studio) ? (
            <LandingSection
              id="contato"
              labelledBy="editorial-contato"
              className="editorial-hairline mx-auto mt-20 max-w-[var(--editorial-measure)] border-t pt-10"
            >
              <h2
                id="editorial-contato"
                className={`${studio.fontHeadingClass} mb-4 text-2xl`}
              >
                {studio.contact.title}
              </h2>
              {studio.contact.body ? (
                <p className="mb-6 leading-7 text-[var(--studio-muted)]">
                  {studio.contact.body}
                </p>
              ) : null}
              {studio.contact.href ? (
                <a
                  href={studio.contact.href}
                  className={`inline-block border-b border-[var(--studio-primary)] pb-0.5 text-[var(--studio-primary)] ${FOCUS_RING}`}
                >
                  {studio.contact.cta}
                </a>
              ) : (
                <p>{studio.contact.cta}</p>
              )}
            </LandingSection>
          ) : null}

          {showMap(studio) && studio.map ? (
            <LandingSection id="mapa" labelledBy="editorial-mapa" className="mt-16">
              <h2
                id="editorial-mapa"
                className={`${studio.fontHeadingClass} mb-4 text-xl`}
              >
                {studio.map.address}
              </h2>
              <MapLink
                address={studio.map.address}
                mapsUrl={studio.map.mapsUrl}
                embedUrl={studio.map.embedUrl}
                className="grid gap-4"
                linkClassName="text-[var(--studio-primary)] underline-offset-4 hover:underline"
                iframeClassName="h-56 w-full max-w-full rounded-[var(--studio-radius)] border-0"
              />
            </LandingSection>
          ) : null}
        </main>
      </article>
    </StudioFrame>
  );
}
