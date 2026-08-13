import type { ReactNode } from "react";

type LandingSectionProps = {
  id: string;
  children: ReactNode;
  className?: string;
  labelledBy?: string;
};

export function LandingSection({
  id,
  children,
  className,
  labelledBy,
}: LandingSectionProps) {
  return (
    <section id={id} className={className} aria-labelledby={labelledBy}>
      {children}
    </section>
  );
}
