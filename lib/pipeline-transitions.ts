import type { PipelineStatus } from "@/lib/schemas";
import { REPOSITORY_ERROR_CODES, RepositoryError } from "@/lib/json-atomic";

/** Happy path from plan.md §7, matching `pipeline/.../state_machine.py`. */
const HAPPY_PATH: ReadonlyArray<readonly [PipelineStatus, PipelineStatus]> = [
  ["imported", "queued"],
  ["queued", "discovering"],
  ["discovering", "scraping"],
  ["scraping", "enriching"],
  ["enriching", "selecting_media"],
  ["selecting_media", "generating"],
  ["generating", "validating"],
  ["validating", "ready_for_review"],
  ["ready_for_review", "approved"],
  ["approved", "deploying"],
  ["deploying", "deployed"],
];

const OPERATIONAL_STATUSES: readonly PipelineStatus[] = [
  "queued",
  "discovering",
  "needs_social_review",
  "scraping",
  "enriching",
  "selecting_media",
  "generating",
  "validating",
  "deploying",
];

const EXTRA_TRANSITIONS: ReadonlyArray<readonly [PipelineStatus, PipelineStatus]> = [
  ["discovering", "needs_social_review"],
  ["needs_social_review", "discovering"],
  ["failed", "queued"],
  ["ready_for_review", "rejected"],
  ["rejected", "queued"],
  ["approved", "ready_for_review"],
  ["deploying", "approved"],
];

function pairKey(from: PipelineStatus, to: PipelineStatus): string {
  return `${from}\u2192${to}`;
}

const ALLOWED_PAIRS: ReadonlySet<string> = new Set([
  ...HAPPY_PATH.map(([from, to]) => pairKey(from, to)),
  ...EXTRA_TRANSITIONS.map(([from, to]) => pairKey(from, to)),
  ...OPERATIONAL_STATUSES.map((from) => pairKey(from, "failed")),
]);

function destinations(from: PipelineStatus): PipelineStatus[] {
  const all: PipelineStatus[] = [
    "imported",
    "queued",
    "discovering",
    "needs_social_review",
    "scraping",
    "enriching",
    "selecting_media",
    "generating",
    "validating",
    "ready_for_review",
    "approved",
    "rejected",
    "deploying",
    "deployed",
    "failed",
  ];
  return all.filter((to) => ALLOWED_PAIRS.has(pairKey(from, to)));
}

/** Explicit adjacency list (plan §7). Same edges as the Python table. */
export const ALLOWED_TRANSITIONS: {
  readonly [K in PipelineStatus]: readonly PipelineStatus[];
} = {
  imported: destinations("imported"),
  queued: destinations("queued"),
  discovering: destinations("discovering"),
  needs_social_review: destinations("needs_social_review"),
  scraping: destinations("scraping"),
  enriching: destinations("enriching"),
  selecting_media: destinations("selecting_media"),
  generating: destinations("generating"),
  validating: destinations("validating"),
  ready_for_review: destinations("ready_for_review"),
  approved: destinations("approved"),
  rejected: destinations("rejected"),
  deploying: destinations("deploying"),
  deployed: destinations("deployed"),
  failed: destinations("failed"),
};

/** CLI may repeat queue without appending history (Python `IDEMPOTENT_TRANSITIONS`). */
export const IDEMPOTENT_TRANSITIONS: ReadonlySet<string> = new Set([pairKey("queued", "queued")]);

const AUTOMATED_ACTORS = new Set(["pipeline", "cli"]);

export function actorBase(actor: string): string {
  const colon = actor.indexOf(":");
  return colon === -1 ? actor : actor.slice(0, colon);
}

/** `pipeline` / `cli` and `pipeline:*` / `cli:*` are non-human. */
export function isAutomatedActor(actor: string): boolean {
  return AUTOMATED_ACTORS.has(actorBase(actor));
}

export function isIdempotentTransition(from: PipelineStatus, to: PipelineStatus): boolean {
  return IDEMPOTENT_TRANSITIONS.has(pairKey(from, to));
}

export function isAllowedTransition(
  from: PipelineStatus,
  to: PipelineStatus,
  actor?: string,
): boolean {
  if (!ALLOWED_PAIRS.has(pairKey(from, to))) {
    return false;
  }
  if (
    from === "ready_for_review" &&
    to === "approved" &&
    actor !== undefined &&
    isAutomatedActor(actor)
  ) {
    return false;
  }
  return true;
}

export function assertCanTransition(
  from: PipelineStatus,
  to: PipelineStatus,
  actor: string,
): void {
  if (isIdempotentTransition(from, to)) {
    return;
  }
  if (isAllowedTransition(from, to, actor)) {
    return;
  }
  if (from === "ready_for_review" && to === "approved" && isAutomatedActor(actor)) {
    throw new RepositoryError(
      REPOSITORY_ERROR_CODES.INPUT_INVALID,
      "ready_for_review → approved requires a human actor; pipeline cannot approve",
    );
  }
  throw new RepositoryError(
    REPOSITORY_ERROR_CODES.INPUT_INVALID,
    `illegal pipeline transition: ${from} → ${to}`,
  );
}
