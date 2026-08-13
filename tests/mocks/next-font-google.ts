function fakeFont(name: string) {
  return (options?: { variable?: string }) => ({
    className: `mock-font-${name}`,
    variable: options?.variable ?? `--font-${name}`,
    style: { fontFamily: name },
  });
}

export const Fraunces = fakeFont("fraunces");
export const Newsreader = fakeFont("newsreader");
export const Source_Sans_3 = fakeFont("source-sans-3");
export const Outfit = fakeFont("outfit");
export const Bebas_Neue = fakeFont("bebas-neue");
export const Archivo_Black = fakeFont("archivo-black");
export const IBM_Plex_Sans = fakeFont("ibm-plex-sans");
export const Literata = fakeFont("literata");
