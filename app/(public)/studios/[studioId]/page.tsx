import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { StudioLanding } from "@/components/landing/studio-landing";
import { loadCatalog } from "@/lib/catalog";
import { loadApprovedViewModel } from "@/lib/studio-loader";

export const dynamicParams = false;

export async function generateStaticParams() {
  const catalog = await loadCatalog();
  return catalog.studios.map(({ studioId }) => ({ studioId }));
}

export async function generateMetadata({ params }: PageProps<"/studios/[studioId]">): Promise<Metadata> {
  const { studioId } = await params;
  const studio = await loadApprovedViewModel(studioId);
  if (!studio) return { title: "Estúdio não encontrado" };
  return {
    title: studio.seo.title,
    description: studio.seo.description,
    alternates: { canonical: `/studios/${studioId}` },
    openGraph: {
      title: studio.seo.title,
      description: studio.seo.description,
      type: "website",
      ...(studio.seo.ogImage ? { images: [{ url: studio.seo.ogImage }] } : {}),
    },
  };
}

export default async function StudioPage({ params }: PageProps<"/studios/[studioId]">) {
  const { studioId } = await params;
  const studio = await loadApprovedViewModel(studioId);
  if (!studio) notFound();
  return <StudioLanding studio={studio} />;
}
