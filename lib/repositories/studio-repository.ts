import { join } from "node:path";
import { assertSafeStudioId, readJsonDocument, writeJsonDocument } from "@/lib/json-atomic";
import type {
  ApprovedSite,
  Deployment,
  Dossier,
  GeneratedSite,
  Studio,
} from "@/lib/schemas";

/** Persistence port for per-studio JSON documents. */
export interface StudioRepository {
  getStudio(studioId: string): Promise<Studio | null>;
  saveStudio(studio: Studio, expectedUpdatedAt?: string): Promise<void>;
  getDossier(studioId: string): Promise<Dossier | null>;
  saveDossier(dossier: Dossier, expectedUpdatedAt?: string): Promise<void>;
  getGenerated(studioId: string): Promise<GeneratedSite | null>;
  saveGenerated(generated: GeneratedSite, expectedUpdatedAt?: string): Promise<void>;
  getApproved(studioId: string): Promise<ApprovedSite | null>;
  saveApproved(approved: ApprovedSite, expectedUpdatedAt?: string): Promise<void>;
  getDeployment(studioId: string): Promise<Deployment | null>;
  saveDeployment(deployment: Deployment, expectedUpdatedAt?: string): Promise<void>;
}

export class JsonStudioRepository implements StudioRepository {
  readonly dataDir: string;

  constructor(dataDir: string = process.env.DATA_DIR ?? "data") {
    this.dataDir = dataDir;
  }

  private studioDir(studioId: string): string {
    assertSafeStudioId(studioId);
    return join(this.dataDir, "studios", studioId);
  }

  private docPath(studioId: string, filename: string): string {
    return join(this.studioDir(studioId), filename);
  }

  getStudio(studioId: string): Promise<Studio | null> {
    return readJsonDocument<Studio>(this.docPath(studioId, "studio.json"), "studio");
  }

  saveStudio(studio: Studio, expectedUpdatedAt?: string): Promise<void> {
    return writeJsonDocument({
      filePath: this.docPath(studio.studioId, "studio.json"),
      data: studio,
      schemaKind: "studio",
      expectedUpdatedAt,
    });
  }

  getDossier(studioId: string): Promise<Dossier | null> {
    return readJsonDocument<Dossier>(this.docPath(studioId, "dossier.json"), "dossier");
  }

  saveDossier(dossier: Dossier, expectedUpdatedAt?: string): Promise<void> {
    return writeJsonDocument({
      filePath: this.docPath(dossier.studioId, "dossier.json"),
      data: dossier,
      schemaKind: "dossier",
      expectedUpdatedAt,
    });
  }

  getGenerated(studioId: string): Promise<GeneratedSite | null> {
    return readJsonDocument<GeneratedSite>(this.docPath(studioId, "generated.json"), "generated");
  }

  saveGenerated(generated: GeneratedSite, expectedUpdatedAt?: string): Promise<void> {
    return writeJsonDocument({
      filePath: this.docPath(generated.studioId, "generated.json"),
      data: generated,
      schemaKind: "generated",
      expectedUpdatedAt,
    });
  }

  getApproved(studioId: string): Promise<ApprovedSite | null> {
    return readJsonDocument<ApprovedSite>(this.docPath(studioId, "approved.json"), "approved");
  }

  saveApproved(approved: ApprovedSite, expectedUpdatedAt?: string): Promise<void> {
    return writeJsonDocument({
      filePath: this.docPath(approved.studioId, "approved.json"),
      data: approved,
      schemaKind: "approved",
      expectedUpdatedAt,
    });
  }

  getDeployment(studioId: string): Promise<Deployment | null> {
    return readJsonDocument<Deployment>(this.docPath(studioId, "deployment.json"), "deployment");
  }

  saveDeployment(deployment: Deployment, expectedUpdatedAt?: string): Promise<void> {
    return writeJsonDocument({
      filePath: this.docPath(deployment.studioId, "deployment.json"),
      data: deployment,
      schemaKind: "deployment",
      expectedUpdatedAt,
    });
  }
}
