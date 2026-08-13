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
import "./bold.css";

export function BoldTemplate({ studio }: LandingTemplateProps) {
  const ctaHref = heroCtaHref(studio);

  return (
    <StudioFrame studio={studio} className="bold-root">
      <main id="conteudo" className="w-full max-w-full">
        <header className="bold-slab overflow-hidden bg-[var(--studio-primary)] text-[var(--studio-bg)]">
          <div className="grid gap-8 px-4 py-12 sm:px-8 sm:py-16 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,0.8fr)] lg:items-end lg:px-12 lg:py-20">
            <div className="min-w-0">
              {studio.hero.eyebrow ? (
                <p className="mb-4 text-xs font-semibold uppercase tracking-[0.28em]">
                  {studio.hero.eyebrow}
                </p>
              ) : null}
              <h1
                className={`${studio.fontHeadingClass} text-balance text-[clamp(2.8rem,11vw,7.2rem)] uppercase leading-[0.86] tracking-[-0.04em]`}
              >
                {studio.hero.title}
              </h1>
            </div>
            <div className="min-w-0 pb-6">
              {studio.hero.subtitle ? (
                <p className="mb-6 text-lg leading-7">{studio.hero.subtitle}</p>
              ) : null}
              {studio.hero.primaryCta && ctaHref ? (
                <a
                  href={ctaHref}
                  className={`inline-flex w-full items-center justify-center bg-[var(--studio-bg)] px-6 py-5 text-center text-lg font-semibold uppercase tracking-wide text-[var(--studio-primary)] sm:w-auto ${FOCUS_RING}`}
                >
                  {studio.hero.primaryCta}
                </a>
              ) : null}
            </div>
          </div>
        </header>

        {studio.hero.image ? (
          <div className="relative z-10 mx-4 -mt-8 max-w-3xl sm:mx-8 lg:ml-auto lg:mr-12">
            <StudioImg
              image={studio.hero.image}
              priority
              className="bold-stamp h-auto w-full max-w-full"
              sizes="(max-width: 768px) 100vw, 48rem"
            />
          </div>
        ) : null}

        {showAbout(studio) && studio.about ? (
          <LandingSection
            id="sobre"
            labelledBy="bold-sobre"
            className="grid gap-8 px-4 py-16 sm:px-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:px-12"
          >
            <h2
              id="bold-sobre"
              className={`${studio.fontHeadingClass} text-4xl uppercase leading-none sm:text-5xl`}
            >
              {studio.about.title}
            </h2>
            <p className="text-lg leading-8">{studio.about.body}</p>
          </LandingSection>
        ) : null}

        {showGallery(studio) ? (
          <LandingSection id="galeria" labelledBy="bold-galeria" className="overflow-hidden px-4 sm:px-8 lg:px-12">
            <h2 id="bold-galeria" className="sr-only">
              Galeria
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {studio.gallery.map((image, index) => (
                <div
                  key={`${image.src}-${index}`}
                  className={`min-w-0 ${index === 0 ? "sm:col-span-2" : ""} ${index % 3 === 2 ? "sm:translate-x-6" : ""}`}
                >
                  <StudioImg
                    image={image}
                    className="h-auto w-full max-w-full"
                    sizes={
                      index === 0
                        ? "(max-width: 768px) 100vw, 72rem"
                        : "(max-width: 768px) 100vw, 36rem"
                    }
                  />
                </div>
              ))}
            </div>
          </LandingSection>
        ) : null}

        {showPricing(studio) && studio.pricing ? (
          <LandingSection
            id="precos"
            labelledBy="bold-precos"
            className="bold-band my-10 overflow-hidden bg-[var(--studio-secondary)] py-10 text-[var(--studio-bg)]"
          >
            <div className="bold-band-inner px-4 sm:px-8 lg:px-12">
              <h2
                id="bold-precos"
                className={`${studio.fontHeadingClass} mb-8 text-4xl uppercase`}
              >
                {studio.pricing.title}
              </h2>
              <div className="grid gap-6 sm:grid-cols-2">
                {studio.pricing.items.map((item) => (
                  <article
                    key={`${item.label}-${item.value}`}
                    className="bold-stamp bg-[var(--studio-bg)] p-6 text-[var(--studio-text)]"
                  >
                    <p className="text-sm uppercase tracking-widest text-[var(--studio-muted)]">
                      {item.label}
                    </p>
                    <p className={`${studio.fontHeadingClass} mt-2 text-4xl`}>
                      {item.value}
                    </p>
                    {item.note ? <p className="mt-3 text-sm">{item.note}</p> : null}
                  </article>
                ))}
              </div>
            </div>
          </LandingSection>
        ) : null}

        {showEquipment(studio) && studio.equipment ? (
          <LandingSection
            id="equipamentos"
            labelledBy="bold-equipamentos"
            className="px-4 py-12 sm:px-8 lg:px-12"
          >
            <h2
              id="bold-equipamentos"
              className={`${studio.fontHeadingClass} mb-6 text-3xl uppercase`}
            >
              {studio.equipment.title}
            </h2>
            {studio.equipment.intro ? (
              <p className="mb-6 max-w-xl">{studio.equipment.intro}</p>
            ) : null}
            <ul className="flex flex-wrap gap-3">
              {studio.equipment.items.map((item) => (
                <li
                  key={item}
                  className="bg-[var(--studio-primary)] px-4 py-2 text-sm font-semibold uppercase tracking-wide text-[var(--studio-bg)]"
                >
                  {item}
                </li>
              ))}
            </ul>
          </LandingSection>
        ) : null}

        {showReviews(studio) && studio.reviews ? (
          <LandingSection id="avaliacoes" labelledBy="bold-avaliacoes" className="px-4 py-8 sm:px-8 lg:px-12">
            <h2
              id="bold-avaliacoes"
              className={`${studio.fontHeadingClass} mb-6 text-3xl uppercase`}
            >
              {studio.reviews.title}
            </h2>
            {typeof studio.reviews.rating === "number" ? (
              <p className={`${studio.fontHeadingClass} mb-6 text-7xl text-[var(--studio-primary)]`}>
                {studio.reviews.rating.toLocaleString("pt-BR", {
                  minimumFractionDigits: 1,
                  maximumFractionDigits: 1,
                })}
              </p>
            ) : null}
            {typeof studio.reviews.count === "number" ? (
              <p className="mb-8 text-sm uppercase tracking-widest text-[var(--studio-muted)]">
                {studio.reviews.count} avaliações
              </p>
            ) : null}
            <div className="grid gap-4">
              {studio.reviews.excerpts?.map((excerpt) => (
                <p
                  key={excerpt}
                  className="bg-[var(--studio-surface)] px-5 py-6 text-xl leading-snug"
                >
                  {excerpt}
                </p>
              ))}
            </div>
          </LandingSection>
        ) : null}

        {showHours(studio) && studio.hours ? (
          <LandingSection
            id="horarios"
            labelledBy="bold-horarios"
            className="bold-counter bg-[var(--studio-surface)] px-4 py-14 sm:px-8 lg:px-12"
          >
            <h2
              id="bold-horarios"
              className={`${studio.fontHeadingClass} mb-8 text-3xl uppercase`}
            >
              {studio.hours.title}
            </h2>
            <dl className="grid gap-4 sm:grid-cols-2">
              {studio.hours.items.map((item) => (
                <div
                  key={`${item.day}-${item.value}`}
                  className="border-4 border-[var(--studio-primary)] p-4"
                >
                  <dt className="text-xs uppercase tracking-widest text-[var(--studio-muted)]">
                    {item.day}
                  </dt>
                  <dd className={`${studio.fontHeadingClass} mt-2 text-2xl`}>
                    {item.value}
                  </dd>
                </div>
              ))}
            </dl>
          </LandingSection>
        ) : null}

        {showContact(studio) ? (
          <LandingSection
            id="contato"
            labelledBy="bold-contato"
            className="px-4 py-16 sm:px-8 lg:px-12"
          >
            <h2
              id="bold-contato"
              className={`${studio.fontHeadingClass} mb-4 text-5xl uppercase leading-none`}
            >
              {studio.contact.title}
            </h2>
            {studio.contact.body ? (
              <p className="mb-8 max-w-lg text-lg">{studio.contact.body}</p>
            ) : null}
            {studio.contact.href ? (
              <a
                href={studio.contact.href}
                className={`inline-flex w-full items-center justify-center bg-[var(--studio-primary)] px-6 py-6 text-center text-xl font-semibold uppercase tracking-wide text-[var(--studio-bg)] sm:w-auto ${FOCUS_RING}`}
              >
                {studio.contact.cta}
              </a>
            ) : (
              <p className="text-xl uppercase">{studio.contact.cta}</p>
            )}
          </LandingSection>
        ) : null}

        {showMap(studio) && studio.map ? (
          <LandingSection
            id="mapa"
            labelledBy="bold-mapa"
            className="overflow-hidden bg-[var(--studio-primary)] px-4 py-12 text-[var(--studio-bg)] sm:px-8 lg:px-12"
          >
            <h2
              id="bold-mapa"
              className={`${studio.fontHeadingClass} mb-6 text-4xl uppercase`}
            >
              {studio.map.address}
            </h2>
            <MapLink
              address={studio.map.address}
              mapsUrl={studio.map.mapsUrl}
              embedUrl={studio.map.embedUrl}
              className="grid gap-4"
              linkClassName="text-lg font-semibold underline underline-offset-4"
              iframeClassName="h-64 w-full max-w-full border-0"
            />
          </LandingSection>
        ) : null}
      </main>
    </StudioFrame>
  );
}
