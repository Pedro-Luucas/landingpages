import type { ReactNode } from "react";
import {
  archivoBlack,
  bebasNeue,
  fraunces,
  ibmPlexSans,
  literata,
  newsreader,
  outfit,
  sourceSans3,
} from "@/lib/fonts";

export default function PublicLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <div
      lang="pt-BR"
      className={`${fraunces.variable} ${newsreader.variable} ${sourceSans3.variable} ${outfit.variable} ${bebasNeue.variable} ${archivoBlack.variable} ${ibmPlexSans.variable} ${literata.variable} min-h-full`}
    >
      {children}
    </div>
  );
}
