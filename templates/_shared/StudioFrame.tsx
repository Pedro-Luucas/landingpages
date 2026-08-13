import type { CSSProperties, ReactNode } from "react";
import type { StudioViewModel } from "@/lib/view-model";
import { FOCUS_RING } from "./focus";

type StudioFrameProps = {
  studio: StudioViewModel;
  children: ReactNode;
  className?: string;
};

export function StudioFrame({
  studio,
  children,
  className = "",
}: StudioFrameProps) {
  return (
    <div
      lang="pt-BR"
      className={`min-h-dvh overflow-x-hidden ${studio.fontBodyClass} ${className}`.trim()}
      style={
        {
          ...studio.cssVars,
          backgroundColor: "var(--studio-bg)",
          color: "var(--studio-text)",
        } as CSSProperties
      }
    >
      <a
        href="#conteudo"
        className={`sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:bg-[var(--studio-surface)] focus:px-3 focus:py-2 focus:text-[var(--studio-text)] ${FOCUS_RING}`}
      >
        Ir para o conteúdo
      </a>
      {children}
    </div>
  );
}
