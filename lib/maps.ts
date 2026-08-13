export type MapSource = {
  address?: string;
  latitude?: number;
  longitude?: number;
  /** Source embed HTML is never used. */
  embedHtml?: string;
};

export type MapLinks = {
  address: string;
  mapsUrl: string;
  embedUrl: string;
  latitude?: number;
  longitude?: number;
};

const HTML_MARKUP = /<\s*(iframe|script|object|embed|html|body|div|img)\b/i;

function looksLikeHtml(value: string): boolean {
  return HTML_MARKUP.test(value) || /javascript:/i.test(value);
}

function usableAddress(value: string | undefined): string | undefined {
  if (!value) {
    return undefined;
  }
  const trimmed = value.trim();
  if (!trimmed || looksLikeHtml(trimmed)) {
    return undefined;
  }
  return trimmed;
}

function usableCoordinate(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return undefined;
  }
  return value;
}

function searchQuery(source: {
  address?: string;
  latitude?: number;
  longitude?: number;
}): string | undefined {
  if (source.address) {
    return source.address;
  }
  if (source.latitude !== undefined && source.longitude !== undefined) {
    return `${source.latitude},${source.longitude}`;
  }
  return undefined;
}

/**
 * Builds Google Maps search and embed URLs from an address or coordinates.
 * Ignores embed HTML from sources — URLs are always constructed here.
 */
export function buildMapLinks(source: MapSource): MapLinks | null {
  void source.embedHtml;

  const address = usableAddress(source.address);
  const latitude = usableCoordinate(source.latitude);
  const longitude = usableCoordinate(source.longitude);
  const query = searchQuery({ address, latitude, longitude });
  if (!query) {
    return null;
  }

  const encoded = encodeURIComponent(query);
  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encoded}`;
  const embedUrl = `https://www.google.com/maps?q=${encoded}&output=embed`;

  return {
    address: address ?? query,
    mapsUrl,
    embedUrl,
    ...(latitude !== undefined ? { latitude } : {}),
    ...(longitude !== undefined ? { longitude } : {}),
  };
}
