import { existsSync } from "node:fs";
import { join } from "node:path";
import type * as React from "react";
import { toCssVars } from "@/lib/branding";
import { getFontClass } from "@/lib/fonts";
import { buildMapLinks } from "@/lib/maps";
import type { GeneratedSite } from "@/lib/schemas";

export type StudioImage = {
  src: string;
  alt: string;
  width: number;
  height: number;
};

export type StudioViewModel = {
  studioId: string;
  templateId: "editorial" | "immersive" | "minimal" | "bold";
  /** Only --studio-* custom properties. Never dynamic Tailwind color classes. */
  cssVars: React.CSSProperties;
  fontHeadingClass: string;
  fontBodyClass: string;
  hero: {
    eyebrow?: string;
    title: string;
    subtitle?: string;
    primaryCta?: string;
    image?: StudioImage;
  };
  about?: { title: string; body: string };
  gallery: StudioImage[];
  equipment?: { title: string; intro?: string; items: string[] };
  pricing?: { title: string; items: Array<{ label: string; value: string; note?: string }> };
  hours?: { title: string; items: Array<{ day: string; value: string }> };
  reviews?: { title: string; rating?: number; count?: number; excerpts?: string[] };
  contact: { title: string; body?: string; cta: string; href?: string };
  map?: {
    address: string;
    mapsUrl: string;
    embedUrl?: string;
    latitude?: number;
    longitude?: number;
  };
  seo: { title: string; description: string; ogImage?: string };
  /** Ordered ids that have data and are enabled. Hide everything else. */
  enabledSections: string[];
};

export type LandingTemplateProps = { studio: StudioViewModel };

const TEMPLATE_IDS = ["editorial", "immersive", "minimal", "bold"] as const;

export const PLACEHOLDER_IMAGE_SRC = "/fixtures/placeholder.png";
const PLACEHOLDER_WIDTH = 1200;
const PLACEHOLDER_HEIGHT = 800;
const LOGO_WIDTH = 512;
const LOGO_HEIGHT = 512;

export type ToViewModelOptions = {
  templateId?: StudioViewModel["templateId"];
  location?: {
    address?: string;
    latitude?: number;
    longitude?: number;
    embedHtml?: string;
  };
  contacts?: {
    website?: string;
    instagram?: string;
    phone?: string;
  };
  studioName?: string;
  fileExists?: (projectRelativePath: string) => boolean;
};

export function isStudioTemplateId(
  value: string,
): value is StudioViewModel["templateId"] {
  return (TEMPLATE_IDS as readonly string[]).includes(value);
}

export function parseTemplateIdParam(
  value: unknown,
): StudioViewModel["templateId"] | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  if (typeof raw !== "string") {
    return undefined;
  }
  return isStudioTemplateId(raw) ? raw : undefined;
}

function resolveTemplateId(
  generatedId: string,
  override?: StudioViewModel["templateId"],
): StudioViewModel["templateId"] {
  if (override && isStudioTemplateId(override)) {
    return override;
  }
  if (isStudioTemplateId(generatedId)) {
    return generatedId;
  }
  return "editorial";
}

function defaultFileExists(projectRelativePath: string): boolean {
  const relative = toProjectRelativePath(projectRelativePath);
  if (!relative.startsWith("public/")) {
    return false;
  }
  return existsSync(join(process.cwd(), "public", relative.slice("public/".length)));
}

function toProjectRelativePath(assetPath: string): string {
  return assetPath.replace(/\\/g, "/").replace(/^\.?\//, "");
}

function toPublicSrc(assetPath: string): string {
  const normalized = toProjectRelativePath(assetPath);
  if (normalized.startsWith("public/")) {
    return `/${normalized.slice("public/".length)}`;
  }
  if (normalized.startsWith("/")) {
    return normalized;
  }
  return `/${normalized}`;
}

function isLogoAsset(assetPath: string): boolean {
  const normalized = toProjectRelativePath(assetPath);
  const fileName = normalized.split("/").pop() ?? "";
  return /^logo\./i.test(fileName);
}

function resolveStudioImage(
  assetPath: string,
  alt: string,
  kind: "logo" | "photo",
  fileExists: (projectRelativePath: string) => boolean,
): StudioImage {
  const relative = toProjectRelativePath(assetPath);
  const exists = fileExists(relative);
  if (exists) {
    return {
      src: toPublicSrc(relative),
      alt,
      width: kind === "logo" ? LOGO_WIDTH : PLACEHOLDER_WIDTH,
      height: kind === "logo" ? LOGO_HEIGHT : PLACEHOLDER_HEIGHT,
    };
  }
  return {
    src: PLACEHOLDER_IMAGE_SRC,
    alt,
    width: PLACEHOLDER_WIDTH,
    height: PLACEHOLDER_HEIGHT,
  };
}

function contactHref(contacts: ToViewModelOptions["contacts"]): string | undefined {
  if (contacts?.website) {
    return contacts.website;
  }
  if (contacts?.instagram) {
    return contacts.instagram;
  }
  if (contacts?.phone) {
    const tel = contacts.phone.replace(/[^\d+]/g, "");
    return tel ? `tel:${tel}` : undefined;
  }
  return undefined;
}

function seoDescription(copy: GeneratedSite["copy"]): string {
  const source = copy.hero.subtitle ?? copy.about?.body ?? copy.contact.body ?? copy.hero.title;
  const trimmed = source.trim();
  if (trimmed.length <= 160) {
    return trimmed;
  }
  return `${trimmed.slice(0, 159).trimEnd()}…`;
}

function hasReviewData(reviews: GeneratedSite["copy"]["reviews"]): boolean {
  if (!reviews) {
    return false;
  }
  return (
    reviews.rating !== undefined ||
    reviews.count !== undefined ||
    (reviews.excerpts !== undefined && reviews.excerpts.length > 0)
  );
}

export function toViewModel(
  generated: GeneratedSite,
  options: ToViewModelOptions = {},
): StudioViewModel {
  const fileExists = options.fileExists ?? defaultFileExists;
  const displayName = options.studioName?.trim() || generated.copy.hero.title;
  const templateId = resolveTemplateId(generated.templateId, options.templateId);

  const logoPath = generated.assetPaths.find(isLogoAsset);
  const photoPaths = generated.assetPaths.filter((path) => !isLogoAsset(path));

  const gallery = photoPaths.map((path, index) =>
    resolveStudioImage(path, `${displayName} — ${index + 1}`, "photo", fileExists),
  );

  const heroImage = photoPaths[0]
    ? resolveStudioImage(photoPaths[0], displayName, "photo", fileExists)
    : logoPath
      ? resolveStudioImage(logoPath, displayName, "logo", fileExists)
      : undefined;

  const about = generated.copy.about;
  const equipment =
    generated.copy.equipment && generated.copy.equipment.items.length > 0
      ? generated.copy.equipment
      : undefined;
  const pricing =
    generated.copy.pricing && generated.copy.pricing.items.length > 0
      ? generated.copy.pricing
      : undefined;
  const hours =
    generated.copy.hours && generated.copy.hours.items.length > 0
      ? generated.copy.hours
      : undefined;
  const reviews = hasReviewData(generated.copy.reviews)
    ? generated.copy.reviews
    : undefined;

  const mapLinks = buildMapLinks({
    address: options.location?.address,
    latitude: options.location?.latitude,
    longitude: options.location?.longitude,
    embedHtml: options.location?.embedHtml,
  });

  const sectionData: Record<string, boolean> = {
    hero: Boolean(generated.copy.hero.title),
    about: Boolean(about),
    gallery: gallery.length > 0,
    equipment: Boolean(equipment),
    pricing: Boolean(pricing),
    hours: Boolean(hours),
    reviews: Boolean(reviews),
    contact: Boolean(generated.copy.contact.title && generated.copy.contact.cta),
    map: Boolean(mapLinks),
  };

  const enabledSections = [...generated.sections]
    .sort((a, b) => a.order - b.order)
    .filter((section) => section.enabled && sectionData[section.id])
    .map((section) => section.id);

  const include = (id: string) => enabledSections.includes(id);

  const href = contactHref(options.contacts);
  const ogImage = heroImage?.src ?? gallery[0]?.src;

  return {
    studioId: generated.studioId,
    templateId,
    cssVars: toCssVars(generated.branding.colors, generated.branding.radius),
    fontHeadingClass: getFontClass(generated.branding.fontHeading, "heading"),
    fontBodyClass: getFontClass(generated.branding.fontBody, "body"),
    hero: {
      ...(generated.copy.hero.eyebrow ? { eyebrow: generated.copy.hero.eyebrow } : {}),
      title: generated.copy.hero.title,
      ...(generated.copy.hero.subtitle ? { subtitle: generated.copy.hero.subtitle } : {}),
      ...(generated.copy.hero.primaryCta
        ? { primaryCta: generated.copy.hero.primaryCta }
        : {}),
      ...(include("hero") && heroImage ? { image: heroImage } : {}),
    },
    ...(include("about") && about ? { about } : {}),
    gallery: include("gallery") ? gallery : [],
    ...(include("equipment") && equipment ? { equipment } : {}),
    ...(include("pricing") && pricing ? { pricing } : {}),
    ...(include("hours") && hours ? { hours } : {}),
    ...(include("reviews") && reviews ? { reviews } : {}),
    contact: {
      title: generated.copy.contact.title,
      ...(generated.copy.contact.body ? { body: generated.copy.contact.body } : {}),
      cta: generated.copy.contact.cta,
      ...(href ? { href } : {}),
    },
    ...(include("map") && mapLinks ? { map: mapLinks } : {}),
    seo: {
      title: generated.copy.hero.title,
      description: seoDescription(generated.copy),
      ...(ogImage ? { ogImage } : {}),
    },
    enabledSections,
  };
}
