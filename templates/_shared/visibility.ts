import type { StudioViewModel } from "@/lib/view-model";

export function hasSection(studio: StudioViewModel, id: string): boolean {
  return studio.enabledSections.includes(id);
}

export function showAbout(studio: StudioViewModel): boolean {
  return hasSection(studio, "about") && Boolean(studio.about);
}

export function showGallery(studio: StudioViewModel): boolean {
  return hasSection(studio, "gallery") && studio.gallery.length > 0;
}

export function showEquipment(studio: StudioViewModel): boolean {
  return (
    hasSection(studio, "equipment") &&
    Boolean(studio.equipment) &&
    (studio.equipment?.items.length ?? 0) > 0
  );
}

export function showPricing(studio: StudioViewModel): boolean {
  return (
    hasSection(studio, "pricing") &&
    Boolean(studio.pricing) &&
    (studio.pricing?.items.length ?? 0) > 0
  );
}

export function showHours(studio: StudioViewModel): boolean {
  return (
    hasSection(studio, "hours") &&
    Boolean(studio.hours) &&
    (studio.hours?.items.length ?? 0) > 0
  );
}

export function showReviews(studio: StudioViewModel): boolean {
  if (!hasSection(studio, "reviews") || !studio.reviews) {
    return false;
  }
  const { excerpts, rating, count } = studio.reviews;
  return (
    (excerpts?.length ?? 0) > 0 ||
    typeof rating === "number" ||
    typeof count === "number"
  );
}

export function showContact(studio: StudioViewModel): boolean {
  return hasSection(studio, "contact");
}

export function showMap(studio: StudioViewModel): boolean {
  return hasSection(studio, "map") && Boolean(studio.map?.mapsUrl);
}

export function heroCtaHref(studio: StudioViewModel): string | undefined {
  if (showContact(studio)) {
    return "#contato";
  }
  return studio.contact.href;
}
