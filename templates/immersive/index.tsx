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
import "./immersive.css";

const FRAME_ROTATION = ["-rotate-2", "rotate-1", "rotate-3", "-rotate-1", "rotate-2"];

export function ImmersiveTemplate({ studio }: LandingTemplateProps) {
  const ctaHref = heroCtaHref(studio);
  const heroImage = studio.hero.image;

  return (
    <StudioFrame studio={studio} className="immersive-root">
      <main id="conteudo" className="relative w-full max-w-full">
        <header className="immersive-hero immersive-vignette relative min-h-[100dvh] overflow-hidden">
          {heroImage ? (
            <StudioImg
              image={heroImage}
              priority
              className="absolute inset-0 h-full w-full max-w-full object-cover"
              sizes="100vw"
            />
          ) : (
            <div
              aria-hidden
              className="absolute inset-0 bg-[var(--studio-surface)]"
            />
          )}
          <div className="immersive-scrim absolute inset-0" />
          <div className="relative z-10 flex min-h-[100dvh] flex-col justify-end px-4 pb-12 pt-24 sm:px-8 lg:px-14">
            {studio.hero.eyebrow ? (
              <p className="mb-3 text-[0.7rem] uppercase tracking-[0.42em] text-[var(--studio-muted)]">
                {studio.hero.eyebrow}
              </p>
            ) : null}
            <h1
              className={`${studio.fontHeadingClass} max-w-4xl text-balance text-[clamp(2.6rem,10vw,6.2rem)] leading-[0.9] text-[var(--studio-text)]`}
            >
              {studio.hero.title}
            </h1>
            {studio.hero.subtitle ? (
              <p className="mt-5 max-w-lg text-base leading-7 text-[var(--studio-muted)]">
                {studio.hero.subtitle}
              </p>
            ) : null}
            {studio.hero.primaryCta && ctaHref ? (
              <a
                href={ctaHref}
                className={`mt-8 inline-flex w-fit bg-[var(--studio-primary)] px-5 py-3 text-sm font-medium text-[var(--studio-bg)] ${FOCUS_RING}`}
              >
                {studio.hero.primaryCta}
              </a>
            ) : null}
          </div>
        </header>

        <div className="immersive-sprocket h-3 w-full opacity-70" aria-hidden />

        {showGallery(studio) ? (
          <LandingSection id="galeria" labelledBy="immersive-galeria" className="relative px-4 py-16 sm:px-8">
            <h2 id="immersive-galeria" className="sr-only">
              Galeria
            </h2>
            <div className="relative mx-auto max-w-6xl">
              {studio.gallery.map((image, index) => (
                <figure
                  key={`${image.src}-${index}`}
                  className={`immersive-frame relative mb-[-12vw] w-[min(88%,28rem)] p-2 sm:mb-[-6rem] sm:w-[min(70%,34rem)] sm:p-3 ${FRAME_ROTATION[index % FRAME_ROTATION.length]} ${index % 2 === 1 ? "ml-auto" : ""}`}
                >
                  <StudioImg
                    image={image}
                    className="h-auto w-full max-w-full object-cover"
                    sizes="(max-width: 768px) 88vw, 34rem"
                  />
                  <figcaption className="mt-2 px-1 text-[0.7rem] uppercase tracking-[0.18em] text-[var(--studio-muted)]">
                    {image.alt}
                  </figcaption>
                </figure>
              ))}
            </div>
          </LandingSection>
        ) : null}

        {showAbout(studio) && studio.about ? (
          <LandingSection
            id="sobre"
            labelledBy="immersive-sobre"
            className="relative z-10 mx-4 mt-24 max-w-xl bg-[var(--studio-surface)] p-6 sm:mx-8 sm:p-10 md:ml-[12vw]"
          >
            <h2
              id="immersive-sobre"
              className={`${studio.fontHeadingClass} mb-4 text-3xl leading-tight`}
            >
              {studio.about.title}
            </h2>
            <p className="leading-8 text-[var(--studio-muted)]">{studio.about.body}</p>
          </LandingSection>
        ) : null}

        {showEquipment(studio) && studio.equipment ? (
          <LandingSection
            id="equipamentos"
            labelledBy="immersive-equipamentos"
            className="px-4 py-20 sm:px-8"
          >
            <h2
              id="immersive-equipamentos"
              className={`${studio.fontHeadingClass} mb-3 text-sm uppercase tracking-[0.35em]`}
            >
              {studio.equipment.title}
            </h2>
            {studio.equipment.intro ? (
              <p className="mb-8 max-w-md text-[var(--studio-muted)]">
                {studio.equipment.intro}
              </p>
            ) : null}
            <ol className="immersive-sheet grid grid-cols-1 gap-px sm:grid-cols-2">
              {studio.equipment.items.map((item, index) => (
                <li
                  key={item}
                  className="flex gap-4 bg-[var(--studio-bg)] px-4 py-5"
                >
                  <span className="text-[var(--studio-primary)]">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span>{item}</span>
                </li>
              ))}
            </ol>
          </LandingSection>
        ) : null}

        {showReviews(studio) && studio.reviews ? (
          <LandingSection
            id="avaliacoes"
            labelledBy="immersive-avaliacoes"
            className="px-4 py-12 sm:px-8"
          >
            <h2
              id="immersive-avaliacoes"
              className={`${studio.fontHeadingClass} mb-8 text-sm uppercase tracking-[0.35em]`}
            >
              {studio.reviews.title}
            </h2>
            {typeof studio.reviews.rating === "number" ? (
              <p className={`${studio.fontHeadingClass} mb-8 text-5xl text-[var(--studio-primary)]`}>
                {studio.reviews.rating.toLocaleString("pt-BR", {
                  minimumFractionDigits: 1,
                  maximumFractionDigits: 1,
                })}
                {typeof studio.reviews.count === "number" ? (
                  <span className="ml-3 text-base font-normal text-[var(--studio-muted)]">
                    {studio.reviews.count}
                  </span>
                ) : null}
              </p>
            ) : null}
            <div className="grid gap-6 md:grid-cols-2">
              {studio.reviews.excerpts?.map((excerpt) => (
                <p
                  key={excerpt}
                  className="border-l border-[var(--studio-primary)] pl-4 text-sm leading-7 text-[var(--studio-muted)]"
                >
                  {excerpt}
                </p>
              ))}
            </div>
          </LandingSection>
        ) : null}

        <div className="grid gap-0 md:grid-cols-2">
          {showPricing(studio) && studio.pricing ? (
            <LandingSection
              id="precos"
              labelledBy="immersive-precos"
              className="bg-[var(--studio-surface)] px-4 py-12 sm:px-8"
            >
              <h2
                id="immersive-precos"
                className={`${studio.fontHeadingClass} mb-6 text-sm uppercase tracking-[0.35em]`}
              >
                {studio.pricing.title}
              </h2>
              <ul className="space-y-4">
                {studio.pricing.items.map((item) => (
                  <li key={`${item.label}-${item.value}`}>
                    <p className="flex justify-between gap-4">
                      <span>{item.label}</span>
                      <span className="text-[var(--studio-primary)]">{item.value}</span>
                    </p>
                    {item.note ? (
                      <p className="text-sm text-[var(--studio-muted)]">{item.note}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </LandingSection>
          ) : null}

          {showHours(studio) && studio.hours ? (
            <LandingSection
              id="horarios"
              labelledBy="immersive-horarios"
              className="px-4 py-12 sm:px-8"
            >
              <h2
                id="immersive-horarios"
                className={`${studio.fontHeadingClass} mb-6 text-sm uppercase tracking-[0.35em]`}
              >
                {studio.hours.title}
              </h2>
              <dl className="space-y-3">
                {studio.hours.items.map((item) => (
                  <div key={`${item.day}-${item.value}`} className="flex justify-between gap-4">
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
            labelledBy="immersive-contato"
            className="relative overflow-hidden px-4 py-20 sm:px-8"
          >
            <h2
              id="immersive-contato"
              className={`${studio.fontHeadingClass} mb-4 text-4xl`}
            >
              {studio.contact.title}
            </h2>
            {studio.contact.body ? (
              <p className="mb-8 max-w-md text-[var(--studio-muted)]">
                {studio.contact.body}
              </p>
            ) : null}
            {studio.contact.href ? (
              <a
                href={studio.contact.href}
                className={`inline-flex bg-[var(--studio-primary)] px-6 py-4 text-[var(--studio-bg)] ${FOCUS_RING}`}
              >
                {studio.contact.cta}
              </a>
            ) : (
              <p>{studio.contact.cta}</p>
            )}
          </LandingSection>
        ) : null}

        {showMap(studio) && studio.map ? (
          <LandingSection id="mapa" labelledBy="immersive-mapa" className="px-4 pb-16 sm:px-8">
            <h2 id="immersive-mapa" className="sr-only">
              {studio.map.address}
            </h2>
            <div className="immersive-frame p-2 sm:p-3">
              <MapLink
                address={studio.map.address}
                mapsUrl={studio.map.mapsUrl}
                embedUrl={studio.map.embedUrl}
                className="grid gap-3"
                linkClassName="px-2 text-sm text-[var(--studio-primary)]"
                iframeClassName="h-64 w-full max-w-full border-0"
              />
            </div>
          </LandingSection>
        ) : null}
      </main>
    </StudioFrame>
  );
}
