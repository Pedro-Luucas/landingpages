import type { LandingTemplateProps } from "@/lib/view-model";

export function FallbackLandingTemplate({ studio }: LandingTemplateProps) {
  return (
    <div
      className={`${studio.fontBodyClass} min-h-full px-6 py-16`}
      style={{
        ...studio.cssVars,
        background: "var(--studio-bg, inherit)",
        color: "var(--studio-text, inherit)",
      }}
    >
      <main className="mx-auto flex max-w-2xl flex-col gap-6">
        {studio.hero.eyebrow ? (
          <p className="text-sm tracking-wide uppercase">{studio.hero.eyebrow}</p>
        ) : null}
        <h1 className={`${studio.fontHeadingClass} text-3xl font-semibold`}>
          {studio.hero.title}
        </h1>
        {studio.hero.subtitle ? <p>{studio.hero.subtitle}</p> : null}
        <section aria-labelledby="enabled-sections-heading">
          <h2 id="enabled-sections-heading" className={studio.fontHeadingClass}>
            Seções
          </h2>
          <ul>
            {studio.enabledSections.map((id) => (
              <li key={id}>{id}</li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
