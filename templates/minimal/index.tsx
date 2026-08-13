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
import "./minimal.css";

export function MinimalTemplate({ studio }: LandingTemplateProps) {
  const ctaHref = heroCtaHref(studio);
  const galleryImages = showGallery(studio)
    ? studio.gallery.filter((image) => image.src !== studio.hero.image?.src)
    : [];

  return (
    <StudioFrame studio={studio} className="minimal-root">
      <main
        id="conteudo"
        className="mx-auto w-full max-w-xl px-6 py-20 sm:py-28"
      >
        {studio.hero.eyebrow ? (
          <p className="minimal-label mb-8 text-[var(--studio-muted)]">
            {studio.hero.eyebrow}
          </p>
        ) : null}

        <h1
          className={`${studio.fontHeadingClass} text-[1.65rem] font-normal leading-snug tracking-tight sm:text-[1.85rem]`}
        >
          {studio.hero.title}
        </h1>

        {studio.hero.subtitle ? (
          <p className="mt-6 text-[0.95rem] leading-7 text-[var(--studio-muted)]">
            {studio.hero.subtitle}
          </p>
        ) : null}

        {studio.hero.primaryCta && ctaHref ? (
          <a
            href={ctaHref}
            className={`mt-8 inline-block text-[0.95rem] underline decoration-[var(--studio-primary)] underline-offset-4 ${FOCUS_RING}`}
          >
            {studio.hero.primaryCta}
          </a>
        ) : null}

        {studio.hero.image ? (
          <figure className="mt-16">
            <StudioImg
              image={studio.hero.image}
              priority
              className="h-auto w-full max-w-full"
              sizes="(max-width: 768px) 100vw, 36rem"
            />
          </figure>
        ) : null}

        {showAbout(studio) && studio.about ? (
          <LandingSection id="sobre" labelledBy="minimal-sobre" className="mt-20">
            <div className="minimal-rule mb-8" />
            <h2
              id="minimal-sobre"
              className={`${studio.fontHeadingClass} mb-5 text-base font-normal`}
            >
              {studio.about.title}
            </h2>
            <p className="text-[0.95rem] leading-7">{studio.about.body}</p>
          </LandingSection>
        ) : null}

        {galleryImages.length > 0 ? (
          <LandingSection id="galeria" labelledBy="minimal-galeria" className="mt-20">
            <h2 id="minimal-galeria" className="sr-only">
              Galeria
            </h2>
            <div className="grid gap-10">
              {galleryImages.map((image, index) => (
                <StudioImg
                  key={`${image.src}-${index}`}
                  image={image}
                  className="h-auto w-full max-w-full"
                  sizes="(max-width: 768px) 100vw, 36rem"
                />
              ))}
            </div>
          </LandingSection>
        ) : null}

        {showEquipment(studio) && studio.equipment ? (
          <LandingSection id="equipamentos" labelledBy="minimal-equipamentos" className="mt-20">
            <h2
              id="minimal-equipamentos"
              className={`${studio.fontHeadingClass} mb-5 text-base font-normal`}
            >
              {studio.equipment.title}
            </h2>
            {studio.equipment.intro ? (
              <p className="mb-5 text-[0.9rem] text-[var(--studio-muted)]">
                {studio.equipment.intro}
              </p>
            ) : null}
            <ul className="space-y-2 text-[0.95rem]">
              {studio.equipment.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </LandingSection>
        ) : null}

        {showPricing(studio) && studio.pricing ? (
          <LandingSection id="precos" labelledBy="minimal-precos" className="mt-20">
            <h2
              id="minimal-precos"
              className={`${studio.fontHeadingClass} mb-5 text-base font-normal`}
            >
              {studio.pricing.title}
            </h2>
            <dl className="space-y-3 text-[0.95rem]">
              {studio.pricing.items.map((item) => (
                <div key={`${item.label}-${item.value}`}>
                  <div className="flex justify-between gap-6">
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                  {item.note ? (
                    <p className="mt-1 text-[0.8rem] text-[var(--studio-muted)]">
                      {item.note}
                    </p>
                  ) : null}
                </div>
              ))}
            </dl>
          </LandingSection>
        ) : null}

        {showHours(studio) && studio.hours ? (
          <LandingSection id="horarios" labelledBy="minimal-horarios" className="mt-20">
            <h2
              id="minimal-horarios"
              className={`${studio.fontHeadingClass} mb-5 text-base font-normal`}
            >
              {studio.hours.title}
            </h2>
            <dl className="space-y-2 text-[0.9rem]">
              {studio.hours.items.map((item) => (
                <div
                  key={`${item.day}-${item.value}`}
                  className="flex justify-between gap-6"
                >
                  <dt className="text-[var(--studio-muted)]">{item.day}</dt>
                  <dd>{item.value}</dd>
                </div>
              ))}
            </dl>
          </LandingSection>
        ) : null}

        {showReviews(studio) && studio.reviews ? (
          <LandingSection id="avaliacoes" labelledBy="minimal-avaliacoes" className="mt-20">
            <h2
              id="minimal-avaliacoes"
              className={`${studio.fontHeadingClass} mb-5 text-base font-normal`}
            >
              {studio.reviews.title}
            </h2>
            {typeof studio.reviews.rating === "number" ||
            typeof studio.reviews.count === "number" ? (
              <p className="mb-6 text-[0.85rem] text-[var(--studio-muted)]">
                {typeof studio.reviews.rating === "number"
                  ? studio.reviews.rating.toLocaleString("pt-BR", {
                      minimumFractionDigits: 1,
                      maximumFractionDigits: 1,
                    })
                  : null}
                {typeof studio.reviews.rating === "number" &&
                typeof studio.reviews.count === "number"
                  ? " / "
                  : null}
                {typeof studio.reviews.count === "number"
                  ? String(studio.reviews.count)
                  : null}
              </p>
            ) : null}
            <div className="space-y-6">
              {studio.reviews.excerpts?.map((excerpt) => (
                <p key={excerpt} className="text-[0.95rem] leading-7 italic">
                  {excerpt}
                </p>
              ))}
            </div>
          </LandingSection>
        ) : null}

        {showContact(studio) ? (
          <LandingSection id="contato" labelledBy="minimal-contato" className="mt-20">
            <div className="minimal-rule mb-8" />
            <h2
              id="minimal-contato"
              className={`${studio.fontHeadingClass} mb-4 text-base font-normal`}
            >
              {studio.contact.title}
            </h2>
            {studio.contact.body ? (
              <p className="mb-5 text-[0.95rem] leading-7 text-[var(--studio-muted)]">
                {studio.contact.body}
              </p>
            ) : null}
            {studio.contact.href ? (
              <a
                href={studio.contact.href}
                className={`text-[0.95rem] underline decoration-[var(--studio-primary)] underline-offset-4 ${FOCUS_RING}`}
              >
                {studio.contact.cta}
              </a>
            ) : (
              <p className="text-[0.95rem]">{studio.contact.cta}</p>
            )}
          </LandingSection>
        ) : null}

        {showMap(studio) && studio.map ? (
          <LandingSection id="mapa" labelledBy="minimal-mapa" className="mt-16">
            <h2 id="minimal-mapa" className="sr-only">
              {studio.map.address}
            </h2>
            <MapLink
              address={studio.map.address}
              mapsUrl={studio.map.mapsUrl}
              embedUrl={studio.map.embedUrl}
              className="grid gap-4"
              linkClassName="text-[0.9rem] underline underline-offset-4"
              iframeClassName="h-48 w-full max-w-full border-0"
            />
          </LandingSection>
        ) : null}
      </main>
    </StudioFrame>
  );
}
