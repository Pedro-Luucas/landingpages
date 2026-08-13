import type { CSSProperties } from "react";
import { describe, expect, it } from "vitest";
import generatedWithPricing from "../../schemas/fixtures/generated.valid.json";
import generatedNoPricingHours from "../../schemas/fixtures/generated.no-pricing-hours.valid.json";
import type { GeneratedSite } from "@/lib/schemas";
import { toViewModel } from "@/lib/view-model";

const withPricing = generatedWithPricing as unknown as GeneratedSite;
const noPricingHours = generatedNoPricingHours as unknown as GeneratedSite;

function cssVar(
  vars: CSSProperties,
  name: string,
): string | number | undefined {
  return (vars as Record<string, string | number | undefined>)[name];
}

describe("toViewModel", () => {
  it("includes pricing when the fixture has pricing data", () => {
    const studio = toViewModel(withPricing);

    expect(studio.pricing).toEqual(withPricing.copy.pricing);
    expect(studio.enabledSections).toContain("pricing");
    expect(studio.enabledSections).toContain("hours");
    expect(studio.hours).toEqual(withPricing.copy.hours);
  });

  it("omits pricing and hours when the no-pricing fixture disables them", () => {
    const studio = toViewModel(noPricingHours);

    expect(studio.pricing).toBeUndefined();
    expect(studio.hours).toBeUndefined();
    expect(studio.enabledSections).not.toContain("pricing");
    expect(studio.enabledSections).not.toContain("hours");
    expect(studio.enabledSections).toContain("equipment");
    expect(studio.enabledSections).toContain("reviews");
  });

  it("honors a templateId override for preview", () => {
    const studio = toViewModel(withPricing, { templateId: "bold" });

    expect(withPricing.templateId).toBe("editorial");
    expect(studio.templateId).toBe("bold");
  });

  it("does not invent a map when no address or coordinates are provided", () => {
    const studio = toViewModel(withPricing);

    expect(studio.map).toBeUndefined();
    expect(studio.enabledSections).not.toContain("map");
  });

  it("builds map links from a provided address and ignores embed HTML", () => {
    const studio = toViewModel(withPricing, {
      location: {
        address: "Rua Fictícia do Ensaio, 240, Curitiba - PR",
        embedHtml:
          '<iframe src="https://maps.google.com/embed?q=injected-place"></iframe>',
      },
    });

    expect(studio.map?.address).toBe(
      "Rua Fictícia do Ensaio, 240, Curitiba - PR",
    );
    expect(studio.map?.mapsUrl).toMatch(
      /^https:\/\/www\.google\.com\/maps\/search\/\?api=1&query=/,
    );
    expect(studio.map?.mapsUrl).not.toContain("injected-place");
    expect(studio.map?.embedUrl).not.toContain("<iframe");
    expect(studio.enabledSections).toContain("map");
  });

  it("drops invalid branding colors from cssVars", () => {
    const generated = structuredClone(withPricing);
    generated.branding.colors.primary = "not-a-hex";
    generated.branding.colors.background = "#0F1419";

    const studio = toViewModel(generated);

    expect(cssVar(studio.cssVars, "--studio-primary")).toBeUndefined();
    expect(cssVar(studio.cssVars, "--studio-bg")).toBe("#0F1419");
    expect(cssVar(studio.cssVars, "--studio-radius")).toBe("12px");
  });

  it("maps an unknown heading font to an allowlisted fallback", () => {
    const studio = toViewModel(noPricingHours);

    expect(noPricingHours.branding.fontHeading).toBe("IBM Plex Serif");
    expect(studio.fontHeadingClass).toBe("mock-font-fraunces");
    expect(studio.fontBodyClass).toBe("mock-font-ibm-plex-sans");
    expect(studio.fontHeadingClass).not.toMatch(/inter|roboto|arial|geist/i);
    expect(studio.fontBodyClass).not.toMatch(/inter|roboto|arial|geist/i);
  });
});
