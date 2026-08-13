import { join } from "node:path";
import { cache } from "react";
import { assertSafeStudioId, readJsonDocument, RepositoryError } from "@/lib/json-atomic";
import { JsonStudioRepository } from "@/lib/repositories/studio-repository";
import type { ApprovedSite, GeneratedSite, Studio } from "@/lib/schemas";
import {
  parseTemplateIdParam,
  toViewModel,
  type StudioViewModel,
  type ToViewModelOptions,
} from "@/lib/view-model";

export const AURORA_FIXTURE_STUDIO_ID = "aurora-sound-lab-cwb";

function fixturesDir(): string {
  return join(process.cwd(), "schemas", "fixtures");
}

function createRepository(): JsonStudioRepository {
  return new JsonStudioRepository(process.env.DATA_DIR ?? "data");
}

export function getStudioIdFromEnv(): string | undefined {
  const value = process.env.STUDIO_ID?.trim();
  return value ? value : undefined;
}

async function readFixtureGenerated(): Promise<GeneratedSite> {
  const path = join(fixturesDir(), "generated.valid.json");
  const generated = await readJsonDocument<GeneratedSite>(path, "generated");
  if (!generated) {
    throw new Error(`missing fixture generated.json at ${path}`);
  }
  return generated;
}

async function readFixtureStudio(): Promise<Studio | null> {
  const path = join(fixturesDir(), "studio.valid.json");
  return readJsonDocument<Studio>(path, "studio");
}

export async function loadGeneratedSite(studioId: string): Promise<GeneratedSite | null> {
  try {
    assertSafeStudioId(studioId);
  } catch (error) {
    if (error instanceof RepositoryError) {
      return null;
    }
    throw error;
  }

  const fromData = await createRepository().getGenerated(studioId);
  if (fromData) {
    return fromData;
  }

  if (studioId === AURORA_FIXTURE_STUDIO_ID) {
    return readFixtureGenerated();
  }

  return null;
}

export async function loadApprovedSite(studioId: string): Promise<ApprovedSite | null> {
  try {
    assertSafeStudioId(studioId);
  } catch (error) {
    if (error instanceof RepositoryError) return null;
    throw error;
  }
  return createRepository().getApproved(studioId);
}

export async function loadStudioRecord(studioId: string): Promise<Studio | null> {
  try {
    assertSafeStudioId(studioId);
  } catch (error) {
    if (error instanceof RepositoryError) {
      return null;
    }
    throw error;
  }

  const fromData = await createRepository().getStudio(studioId);
  if (fromData) {
    return fromData;
  }

  if (studioId === AURORA_FIXTURE_STUDIO_ID) {
    return readFixtureStudio();
  }

  return null;
}

function optionsFromStudio(
  studio: Studio | null,
  templateId?: StudioViewModel["templateId"],
): ToViewModelOptions {
  return {
    ...(templateId ? { templateId } : {}),
    ...(studio?.name ? { studioName: studio.name } : {}),
    ...(studio?.location
      ? {
          location: {
            ...(studio.location.address ? { address: studio.location.address } : {}),
            ...(studio.location.latitude !== undefined
              ? { latitude: studio.location.latitude }
              : {}),
            ...(studio.location.longitude !== undefined
              ? { longitude: studio.location.longitude }
              : {}),
          },
        }
      : {}),
    ...(studio?.contacts
      ? {
          contacts: {
            ...(studio.contacts.website ? { website: studio.contacts.website } : {}),
            ...(studio.contacts.instagram ? { instagram: studio.contacts.instagram } : {}),
            ...(studio.contacts.phone ? { phone: studio.contacts.phone } : {}),
          },
        }
      : {}),
  };
}

const loadStudioViewModelCached = cache(
  async (
    studioId: string,
    templateId?: StudioViewModel["templateId"],
  ): Promise<StudioViewModel | null> => {
    const generated = await loadGeneratedSite(studioId);
    if (!generated) {
      return null;
    }
    const studio = await loadStudioRecord(studioId);
    return toViewModel(generated, optionsFromStudio(studio, templateId));
  },
);

export async function loadStudioViewModel(
  studioId: string,
  options?: { templateId?: StudioViewModel["templateId"] },
): Promise<StudioViewModel | null> {
  return loadStudioViewModelCached(studioId, options?.templateId);
}

const loadApprovedViewModelCached = cache(
  async (studioId: string): Promise<StudioViewModel | null> => {
    const approved = await loadApprovedSite(studioId);
    if (!approved) return null;
    const studio = await loadStudioRecord(studioId);
    return toViewModel(approved, optionsFromStudio(studio));
  },
);

export async function loadApprovedViewModel(studioId: string): Promise<StudioViewModel | null> {
  return loadApprovedViewModelCached(studioId);
}

/** Loads the public landing view model for `STUDIO_ID`, or null when unset/missing. */
export async function loadStudioForBuild(): Promise<StudioViewModel | null> {
  const studioId = getStudioIdFromEnv();
  if (!studioId) {
    return null;
  }
  return loadApprovedViewModel(studioId);
}

export { parseTemplateIdParam };
