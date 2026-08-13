import type { CSSProperties } from "react";
import { describe, expect, it } from "vitest";
import { RADIUS_TOKENS, isValidHexColor, toCssVars } from "@/lib/branding";

function cssVar(
  vars: CSSProperties,
  name: string,
): string | number | undefined {
  return (vars as Record<string, string | number | undefined>)[name];
}

describe("branding hex validation", () => {
  it("accepts 3- and 6-digit hex colors", () => {
    expect(isValidHexColor("#0F1419")).toBe(true);
    expect(isValidHexColor("#fff")).toBe(true);
    expect(isValidHexColor("#E8A54B")).toBe(true);
  });

  it("rejects non-hex colors", () => {
    expect(isValidHexColor("red")).toBe(false);
    expect(isValidHexColor("rgb(0,0,0)")).toBe(false);
    expect(isValidHexColor("#gggggg")).toBe(false);
    expect(isValidHexColor("#ffff")).toBe(false);
    expect(isValidHexColor("")).toBe(false);
  });
});

describe("toCssVars", () => {
  it("maps valid hex colors onto --studio-* custom properties", () => {
    const vars = toCssVars(
      {
        background: "#0F1419",
        surface: "#1A2330",
        primary: "#E8A54B",
        secondary: "#4A7C9B",
        text: "#F4F1EA",
        mutedText: "#9AA4B2",
      },
      "medium",
    );

    expect(cssVar(vars, "--studio-bg")).toBe("#0F1419");
    expect(cssVar(vars, "--studio-surface")).toBe("#1A2330");
    expect(cssVar(vars, "--studio-primary")).toBe("#E8A54B");
    expect(cssVar(vars, "--studio-secondary")).toBe("#4A7C9B");
    expect(cssVar(vars, "--studio-text")).toBe("#F4F1EA");
    expect(cssVar(vars, "--studio-muted")).toBe("#9AA4B2");
    expect(cssVar(vars, "--studio-radius")).toBe(RADIUS_TOKENS.medium);
  });

  it("drops invalid colors and keeps valid ones", () => {
    const vars = toCssVars(
      {
        background: "not-a-color",
        surface: "#1A2330",
        primary: "blue",
        secondary: "#4A7C9B",
        text: "rgb(244, 241, 234)",
        mutedText: "#9AA4B2",
      },
      "small",
    );

    expect(cssVar(vars, "--studio-bg")).toBeUndefined();
    expect(cssVar(vars, "--studio-primary")).toBeUndefined();
    expect(cssVar(vars, "--studio-text")).toBeUndefined();
    expect(cssVar(vars, "--studio-surface")).toBe("#1A2330");
    expect(cssVar(vars, "--studio-secondary")).toBe("#4A7C9B");
    expect(cssVar(vars, "--studio-muted")).toBe("#9AA4B2");
    expect(cssVar(vars, "--studio-radius")).toBe(RADIUS_TOKENS.small);
  });
});
