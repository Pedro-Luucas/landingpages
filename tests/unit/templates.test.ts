import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { getTemplate, TEMPLATE_IDS } from "@/lib/template-registry";
import type { StudioViewModel } from "@/lib/view-model";

const MAPS_URL =
  "https://www.google.com/maps/search/?api=1&query=Rua%20Exemplo%20100%20Curitiba";
const EMBED_URL =
  "https://maps.google.com/maps?q=Rua%20Exemplo%20100%20Curitiba&output=embed";

function mockStudio(
  overrides: Partial<StudioViewModel> = {},
): StudioViewModel {
  return {
    studioId: "aurora-sound-lab-cwb",
    templateId: "editorial",
    cssVars: {
      "--studio-bg": "#0F1419",
      "--studio-surface": "#1A2330",
      "--studio-primary": "#E8A54B",
      "--studio-secondary": "#4A7C9B",
      "--studio-text": "#F4F1EA",
      "--studio-muted": "#9AA4B2",
      "--studio-radius": "12px",
    },
    fontHeadingClass: "font-heading-test",
    fontBodyClass: "font-body-test",
    hero: {
      eyebrow: "Estúdio em Curitiba",
      title: "Grave e ensaie com calma no Aurora Sound Lab",
      subtitle:
        "Sala tratada no Água Verde, com cabine isolada e mesa analógica para sessões de voz, banda e podcast.",
      primaryCta: "Agendar visita",
      image: {
        src: "/studios/aurora-sound-lab-cwb/images/01.webp",
        alt: "Fachada do estúdio",
        width: 1600,
        height: 1000,
      },
    },
    about: {
      title: "Um quarto de hotel para o som",
      body: "O Aurora Sound Lab é um estúdio de gravação em Curitiba voltado a ensaios longos e sessões de voz.",
    },
    gallery: [
      {
        src: "/studios/aurora-sound-lab-cwb/images/02.webp",
        alt: "Sala de gravação",
        width: 1200,
        height: 800,
      },
    ],
    equipment: {
      title: "O que está na sala",
      intro: "Lista publicada no site oficial do estúdio.",
      items: ["Mesa analógica SSL", "Microfone Neumann TLM 103"],
    },
    pricing: {
      title: "Sessões",
      items: [{ label: "Ensaio 2 horas", value: "R$ 120", note: "Inclui sala e PA." }],
    },
    hours: {
      title: "Horários",
      items: [{ day: "Segunda a sexta", value: "10:00–22:00" }],
    },
    reviews: {
      title: "Quem já gravou aqui",
      rating: 4.8,
      count: 42,
      excerpts: ["Sala silenciosa e engenheiro paciente na sessão de voz."],
    },
    contact: {
      title: "Marque um horário",
      body: "Atendimento por telefone ou Instagram.",
      cta: "Falar com o estúdio",
      href: "https://www.aurorasoundlab.example/contato",
    },
    map: {
      address: "Rua Exemplo, 100, Curitiba",
      mapsUrl: MAPS_URL,
      embedUrl: EMBED_URL,
    },
    seo: {
      title: "Aurora Sound Lab",
      description: "Estúdio de gravação em Curitiba.",
    },
    enabledSections: [
      "hero",
      "about",
      "gallery",
      "equipment",
      "pricing",
      "hours",
      "reviews",
      "contact",
      "map",
    ],
    ...overrides,
  };
}

function render(id: string, studio: StudioViewModel): string {
  return renderToStaticMarkup(createElement(getTemplate(id), { studio }));
}

function decodeAttr(value: string): string {
  return value
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'");
}

function hrefs(html: string): string[] {
  return [...html.matchAll(/href="([^"]*)"/g)].map((match) =>
    decodeAttr(match[1] ?? ""),
  );
}

function imgTags(html: string): string[] {
  return [...html.matchAll(/<img\b[^>]*>/gi)].map((match) => match[0]);
}

function iframeTags(html: string): string[] {
  return [...html.matchAll(/<iframe\b[^>]*>/gi)].map((match) => match[0]);
}

describe("landing templates", () => {
  const studio = mockStudio();

  it("registers four templates and falls back to editorial", () => {
    expect([...TEMPLATE_IDS]).toEqual([
      "editorial",
      "immersive",
      "minimal",
      "bold",
    ]);
    expect(getTemplate("editorial")).not.toBe(getTemplate("bold"));
    expect(getTemplate("unknown-template")).toBe(getTemplate("editorial"));
  });

  it("renders the hero title in all four templates", () => {
    for (const id of TEMPLATE_IDS) {
      const html = render(id, studio);
      expect(html).toContain(studio.hero.title);
      expect(html).toMatch(/<h1\b/);
    }
  });

  it("applies cssVars including --studio-bg on the wrapper", () => {
    for (const id of TEMPLATE_IDS) {
      const html = render(id, studio);
      expect(html).toContain("--studio-bg");
      expect(html).toContain("#0F1419");
    }
  });

  it("omits pricing, hours, reviews and gallery when they are not enabled", () => {
    const slim = mockStudio({
      enabledSections: ["hero", "about", "contact", "map"],
    });

    for (const id of TEMPLATE_IDS) {
      const html = render(id, slim);
      expect(html).toContain(slim.hero.title);
      expect(html).not.toContain("Sessões");
      expect(html).not.toContain("R$ 120");
      expect(html).not.toContain("Horários");
      expect(html).not.toContain("Segunda a sexta");
      expect(html).not.toContain("Quem já gravou aqui");
      expect(html).not.toContain("Sala silenciosa e engenheiro paciente na sessão de voz.");
      expect(html).not.toContain("Sala de gravação");
      expect(html).not.toContain("/studios/aurora-sound-lab-cwb/images/02.webp");
    }
  });

  it("does not use dangerouslySetInnerHTML", () => {
    const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
    const files = [
      "templates/editorial/index.tsx",
      "templates/immersive/index.tsx",
      "templates/minimal/index.tsx",
      "templates/bold/index.tsx",
      "templates/_shared/MapLink.tsx",
      "templates/_shared/StudioImg.tsx",
      "templates/_shared/StudioFrame.tsx",
      "templates/_shared/LandingSection.tsx",
    ];

    for (const file of files) {
      const source = readFileSync(join(root, file), "utf8");
      expect(source).not.toContain("dangerouslySetInnerHTML");
    }

    for (const id of TEMPLATE_IDS) {
      expect(render(id, studio)).not.toContain("dangerouslySetInnerHTML");
    }
  });

  it("renders map as a constructed maps URL and a lazy iframe from embedUrl", () => {
    for (const id of TEMPLATE_IDS) {
      const html = render(id, studio);
      expect(hrefs(html)).toContain(MAPS_URL);
      const iframes = iframeTags(html);
      expect(iframes.length).toBeGreaterThan(0);
      for (const tag of iframes) {
        expect(tag).toMatch(/loading="lazy"/);
        expect(tag).toContain(`src="${EMBED_URL.replaceAll("&", "&amp;")}"`);
        expect(tag).not.toContain("srcdoc");
      }
    }
  });

  it("gives images alt, width and height", () => {
    for (const id of TEMPLATE_IDS) {
      const tags = imgTags(render(id, studio));
      expect(tags.length).toBeGreaterThan(0);
      for (const tag of tags) {
        expect(tag).toMatch(/\balt="/);
        expect(tag).toMatch(/\bwidth="/);
        expect(tag).toMatch(/\bheight="/);
      }
    }
  });
});
