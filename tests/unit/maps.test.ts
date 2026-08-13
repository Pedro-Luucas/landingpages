import { describe, expect, it } from "vitest";
import { buildMapLinks } from "@/lib/maps";

describe("buildMapLinks", () => {
  it("constructs a Maps search URL from an address", () => {
    const result = buildMapLinks({
      address: "Rua Fictícia do Ensaio, 240, Curitiba - PR",
    });

    expect(result).not.toBeNull();
    expect(result?.mapsUrl).toBe(
      `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
        "Rua Fictícia do Ensaio, 240, Curitiba - PR",
      )}`,
    );
    expect(result?.embedUrl).toBe(
      `https://www.google.com/maps?q=${encodeURIComponent(
        "Rua Fictícia do Ensaio, 240, Curitiba - PR",
      )}&output=embed`,
    );
    expect(result?.address).toBe("Rua Fictícia do Ensaio, 240, Curitiba - PR");
  });

  it("constructs URLs from coordinates when no address is present", () => {
    const result = buildMapLinks({
      latitude: -25.4298,
      longitude: -49.2714,
    });

    expect(result?.mapsUrl).toBe(
      "https://www.google.com/maps/search/?api=1&query=-25.4298%2C-49.2714",
    );
    expect(result?.embedUrl).toContain("output=embed");
    expect(result?.latitude).toBe(-25.4298);
    expect(result?.longitude).toBe(-49.2714);
  });

  it("ignores embed HTML from a source when it is the only input", () => {
    const result = buildMapLinks({
      embedHtml:
        '<iframe src="https://www.google.com/maps/embed?pb=malicious"></iframe>',
    });

    expect(result).toBeNull();
  });

  it("does not copy embed HTML into constructed URLs when an address is present", () => {
    const result = buildMapLinks({
      address: "Curitiba - PR",
      embedHtml:
        '<iframe src="https://evil.example/embed?q=injected"></iframe>',
    });

    expect(result).not.toBeNull();
    expect(result?.mapsUrl).toContain("/maps/search/");
    expect(JSON.stringify(result)).not.toContain("<iframe");
    expect(JSON.stringify(result)).not.toContain("evil.example");
    expect(JSON.stringify(result)).not.toContain("injected");
  });

  it("rejects an address that is itself embed HTML", () => {
    const result = buildMapLinks({
      address:
        '<iframe src="https://www.google.com/maps/embed?pb=abc"></iframe>',
    });

    expect(result).toBeNull();
  });
});
