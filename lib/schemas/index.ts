/** Shared TypeScript contract matching plan.md section 6 and `schemas/*.schema.json`. */

export type SchemaVersion = 1;

export type PipelineStatus =
  | "imported"
  | "queued"
  | "discovering"
  | "needs_social_review"
  | "scraping"
  | "enriching"
  | "selecting_media"
  | "generating"
  | "validating"
  | "ready_for_review"
  | "approved"
  | "rejected"
  | "deploying"
  | "deployed"
  | "failed";

export type SourceType =
  | "official_site"
  | "instagram"
  | "facebook"
  | "google"
  | "directory"
  | "source_json";

export type Evidence<T> = {
  value: T;
  sourceUrl: string;
  sourceType: SourceType;
  collectedAt: string;
  confidence: number;
  excerpt?: string;
};

export type StudioLocation = {
  city?: string;
  state?: string;
  address?: string;
  latitude?: number;
  longitude?: number;
};

export type StudioContacts = {
  phone?: string;
  website?: string;
  instagram?: string;
  facebook?: string;
};

export type StudioSource = {
  importedAt: string;
  sourceFile: string;
  sourceHash: string;
  originalRecord: unknown;
};

export type Studio = {
  schemaVersion: SchemaVersion;
  studioId: string;
  sourceId?: string;
  name: string;
  type?: string;
  slug: string;
  location: StudioLocation;
  contacts: StudioContacts;
  source: StudioSource;
  commercialScore?: number;
  pipelineStatus: PipelineStatus;
  updatedAt: string;
};

export type PipelineWarning = {
  code: string;
  message: string;
  stage?: string;
  at?: string;
  retryable?: boolean;
};

export type DiscoveryAttempt = {
  at: string;
  method: string;
  query?: string;
  url?: string;
  result: string;
  evidence?: Record<string, unknown>;
};

export type DownloadedAsset = {
  sourceUrl: string;
  sha256: string;
  mime: string;
  sizeBytes: number;
  width?: number;
  height?: number;
  localPath: string;
  licenseOrUse?: string;
  collectedAt: string;
};

export type MediaCandidate = DownloadedAsset & {
  score?: number;
  qualityScore?: number;
  relevanceScore?: number;
  flags?: string[];
  usableAsHero?: boolean;
  usableAsGallery?: boolean;
};

export type SocialPost = {
  externalId: string;
  url: string;
  publishedAt?: string;
  caption?: string;
  media: Array<{
    url: string;
    type: "image" | "video" | "carousel";
    localPath?: string;
  }>;
  collectedAt: string;
};

export type PriceEntry = {
  label: string;
  amountText: string;
  conditions?: string;
};

export type OpeningHoursEntry = {
  day: string;
  intervals: string[];
};

export type GoogleReviewsValue = {
  rating?: number;
  count?: number;
  excerpts?: string[];
};

export type MapValue = {
  latitude?: number;
  longitude?: number;
  address?: string;
  placeId?: string;
};

export type Dossier = {
  schemaVersion: SchemaVersion;
  studioId: string;
  discovery: {
    attempts: DiscoveryAttempt[];
    selectedProfiles: {
      instagram?: Evidence<string>;
      facebook?: Evidence<string>;
    };
    requiresHumanReview: boolean;
  };
  social: {
    bio?: Evidence<string>;
    profileImage?: Evidence<string>;
    highlights: Array<Evidence<{ title: string; text?: string }>>;
    posts: SocialPost[];
  };
  facts: {
    description: Evidence<string>[];
    equipment: Evidence<string[]>[];
    prices: Evidence<PriceEntry[]>[];
    openingHours: Evidence<OpeningHoursEntry[]>[];
    googleReviews: Evidence<GoogleReviewsValue>[];
    map: Evidence<MapValue>[];
  };
  media: {
    logo?: DownloadedAsset;
    candidates: MediaCandidate[];
    selected: DownloadedAsset[];
  };
  warnings: PipelineWarning[];
  completedAt?: string;
};

export type KnownTemplateId = "editorial" | "immersive" | "minimal" | "bold";

export type GeneratedSite = {
  schemaVersion: SchemaVersion;
  studioId: string;
  generationId: string;
  inputHash: string;
  provider: string;
  model: string;
  promptVersion: string;
  templateId: KnownTemplateId | string;
  branding: {
    colors: {
      background: string;
      surface: string;
      primary: string;
      secondary: string;
      text: string;
      mutedText: string;
    };
    fontHeading: string;
    fontBody: string;
    radius: "none" | "small" | "medium" | "large";
    mood: string[];
    imageTreatment?: string;
  };
  copy: {
    hero: {
      eyebrow?: string;
      title: string;
      subtitle?: string;
      primaryCta?: string;
    };
    about?: { title: string; body: string };
    equipment?: { title: string; intro?: string; items: string[] };
    pricing?: {
      title: string;
      items: Array<{ label: string; value: string; note?: string }>;
    };
    hours?: { title: string; items: Array<{ day: string; value: string }> };
    reviews?: {
      title: string;
      rating?: number;
      count?: number;
      excerpts?: string[];
    };
    contact: { title: string; body?: string; cta: string };
  };
  sections: Array<{ id: string; enabled: boolean; order: number }>;
  assetPaths: string[];
  factualClaims: Array<{ path: string; evidenceRefs: [string, ...string[]] }>;
  warnings: string[];
  createdAt: string;
};

export type ApprovedSite = GeneratedSite & {
  approvedAt: string;
  approvedBy: string;
  approvalNote?: string;
  assetHashes: Array<{ path: string; sha256: string }>;
};

export type PipelineError = {
  code: string;
  message: string;
  retryable: boolean;
  stage: string;
  occurredAt: string;
};

export type PipelineHistoryEntry = {
  from?: PipelineStatus;
  to: PipelineStatus;
  at: string;
  actor: string;
  reason?: string;
};

export type PipelineItem = {
  studioId: string;
  status: PipelineStatus;
  currentStage?: string;
  attempt: number;
  retryAt?: string;
  lockedBy?: string;
  lockExpiresAt?: string;
  inputHash?: string;
  lastSuccessfulStage?: string;
  warnings: PipelineWarning[];
  error?: PipelineError;
  history: PipelineHistoryEntry[];
  createdAt: string;
  updatedAt: string;
};

export type PipelineState = {
  schemaVersion: SchemaVersion;
  updatedAt: string;
  items: PipelineItem[];
};

export type DeploymentStatus =
  | "queued"
  | "building"
  | "ready"
  | "error"
  | "canceled";

export type DeploymentEnvironment = "production" | "preview" | "development";

export type DeploymentError = {
  code: string;
  message: string;
  retryable: boolean;
  occurredAt: string;
};

export type DeploymentHistoryEntry = {
  from?: DeploymentStatus;
  to: DeploymentStatus;
  at: string;
  actor: string;
  reason?: string;
};

export type Deployment = {
  schemaVersion: SchemaVersion;
  deploymentId: string;
  generationId: string;
  projectId: string;
  projectName: string;
  url: string;
  gitRef: string;
  status: DeploymentStatus;
  studioId: string;
  environment: DeploymentEnvironment;
  createdAt: string;
  readyAt?: string;
  error?: DeploymentError;
  history: DeploymentHistoryEntry[];
};
