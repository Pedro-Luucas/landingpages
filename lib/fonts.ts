import {
  Archivo_Black,
  Bebas_Neue,
  Fraunces,
  IBM_Plex_Sans,
  Literata,
  Newsreader,
  Outfit,
  Source_Sans_3,
} from "next/font/google";

export const FONT_ALLOWLIST = [
  "Fraunces",
  "Newsreader",
  "Source_Sans_3",
  "Outfit",
  "Bebas_Neue",
  "Archivo_Black",
  "IBM_Plex_Sans",
  "Literata",
] as const;

export type AllowlistedFontId = (typeof FONT_ALLOWLIST)[number];

export const FALLBACK_HEADING_FONT: AllowlistedFontId = "Fraunces";
export const FALLBACK_BODY_FONT: AllowlistedFontId = "Source_Sans_3";

const FONT_LOOKUP: Record<string, AllowlistedFontId> = {
  fraunces: "Fraunces",
  newsreader: "Newsreader",
  sourcesans3: "Source_Sans_3",
  sourcesans: "Source_Sans_3",
  outfit: "Outfit",
  bebasneue: "Bebas_Neue",
  bebas: "Bebas_Neue",
  archivoblack: "Archivo_Black",
  archivo: "Archivo_Black",
  ibmplexsans: "IBM_Plex_Sans",
  literata: "Literata",
};

function fontLookupKey(name: string): string {
  return name.trim().toLowerCase().replace(/[\s_-]+/g, "");
}

export function resolveAllowlistedFont(
  name: string | undefined,
  role: "heading" | "body" = "body",
): AllowlistedFontId {
  if (name) {
    const matched = FONT_LOOKUP[fontLookupKey(name)];
    if (matched) {
      return matched;
    }
  }
  return role === "heading" ? FALLBACK_HEADING_FONT : FALLBACK_BODY_FONT;
}

export const fraunces = Fraunces({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-fraunces",
  preload: false,
});

export const newsreader = Newsreader({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-newsreader",
  preload: false,
});

export const sourceSans3 = Source_Sans_3({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-source-sans-3",
  preload: false,
});

export const outfit = Outfit({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-outfit",
  preload: false,
});

export const bebasNeue = Bebas_Neue({
  weight: "400",
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-bebas-neue",
  preload: false,
});

export const archivoBlack = Archivo_Black({
  weight: "400",
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-archivo-black",
  preload: false,
});

export const ibmPlexSans = IBM_Plex_Sans({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-ibm-plex-sans",
  preload: false,
});

export const literata = Literata({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-literata",
  preload: false,
});

const FONT_INSTANCES: Record<
  AllowlistedFontId,
  { className: string; variable: string }
> = {
  Fraunces: fraunces,
  Newsreader: newsreader,
  Source_Sans_3: sourceSans3,
  Outfit: outfit,
  Bebas_Neue: bebasNeue,
  Archivo_Black: archivoBlack,
  IBM_Plex_Sans: ibmPlexSans,
  Literata: literata,
};

export function getFontClass(
  name: string | undefined,
  role: "heading" | "body" = "body",
): string {
  return FONT_INSTANCES[resolveAllowlistedFont(name, role)].className;
}
