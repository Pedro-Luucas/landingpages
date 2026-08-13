import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { redirect } from "next/navigation";
import { StudioLanding } from "@/components/landing/studio-landing";
import { DASHBOARD_COOKIE, isDashboardSessionAuthorized } from "@/lib/auth";
import { loadStudioViewModel } from "@/lib/studio-loader";
import { parseTemplateIdParam } from "@/lib/view-model";
import type { StudioViewModel } from "@/lib/view-model";

type PreviewPageProps = {
  params: Promise<{ studioId: string }>;
  searchParams: Promise<{ template?: string | string[] }>;
};

function metadataFromStudio(studio: StudioViewModel): Metadata {
  return {
    title: studio.seo.title,
    description: studio.seo.description,
    openGraph: {
      title: studio.seo.title,
      description: studio.seo.description,
      ...(studio.seo.ogImage ? { images: [{ url: studio.seo.ogImage }] } : {}),
    },
  };
}

export async function generateMetadata({
  params,
  searchParams,
}: PreviewPageProps): Promise<Metadata> {
  const { studioId } = await params;
  const query = await searchParams;
  const studio = await loadStudioViewModel(studioId, {
    templateId: parseTemplateIdParam(query.template),
  });
  if (!studio) {
    return {
      title: "Studio preview",
      description: `Preview placeholder for ${studioId}.`,
    };
  }
  return { ...metadataFromStudio(studio), robots: { index: false, follow: false } };
}

export default async function PreviewPage({
  params,
  searchParams,
}: PreviewPageProps) {
  const cookieStore = await cookies();
  if (!isDashboardSessionAuthorized(cookieStore.get(DASHBOARD_COOKIE)?.value)) {
    redirect("/dashboard-login");
  }
  const { studioId } = await params;
  const query = await searchParams;
  const studio = await loadStudioViewModel(studioId, {
    templateId: parseTemplateIdParam(query.template),
  });

  if (!studio) {
    notFound();
  }

  return <StudioLanding studio={studio} />;
}
