import type { CSSProperties } from "react";

declare module "react" {
  interface CSSProperties {
    "--studio-bg"?: string;
    "--studio-surface"?: string;
    "--studio-primary"?: string;
    "--studio-secondary"?: string;
    "--studio-text"?: string;
    "--studio-muted"?: string;
    "--studio-radius"?: string;
  }
}

const HEX_COLOR = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

export const RADIUS_TOKENS = {
  none: "0px",
  small: "4px",
  medium: "12px",
  large: "24px",
} as const;

export type RadiusToken = keyof typeof RADIUS_TOKENS;

export type BrandingColors = {
  background?: string;
  surface?: string;
  primary?: string;
  secondary?: string;
  text?: string;
  mutedText?: string;
};

const COLOR_VARS = [
  ["background", "--studio-bg"],
  ["surface", "--studio-surface"],
  ["primary", "--studio-primary"],
  ["secondary", "--studio-secondary"],
  ["text", "--studio-text"],
  ["mutedText", "--studio-muted"],
] as const;

export function isValidHexColor(value: string): boolean {
  return HEX_COLOR.test(value.trim());
}

/** Returns the trimmed hex string, or undefined when the value is not a hex color. */
export function sanitizeHexColor(value: string | undefined): string | undefined {
  if (!value) {
    return undefined;
  }
  const trimmed = value.trim();
  return isValidHexColor(trimmed) ? trimmed : undefined;
}

export function resolveRadiusToken(radius: string | undefined): RadiusToken {
  if (radius && radius in RADIUS_TOKENS) {
    return radius as RadiusToken;
  }
  return "medium";
}

/**
 * Builds `--studio-*` custom properties. Invalid hex colors are omitted.
 * Never returns dynamic Tailwind color classes.
 */
export function toCssVars(
  colors: BrandingColors,
  radius: string | undefined = "medium",
): CSSProperties {
  const vars: CSSProperties = {
    "--studio-radius": RADIUS_TOKENS[resolveRadiusToken(radius)],
  };

  for (const [key, cssVar] of COLOR_VARS) {
    const hex = sanitizeHexColor(colors[key]);
    if (hex) {
      vars[cssVar] = hex;
    }
  }

  return vars;
}
