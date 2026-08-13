"""Explicit pipeline transition table (plan §7). Never free-assign status."""

from __future__ import annotations

from studio_pipeline.errors import INPUT_INVALID, PipelineError

PIPELINE_STATUSES = (
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
)

HAPPY_PATH: tuple[tuple[str, str], ...] = (
    ("imported", "queued"),
    ("queued", "discovering"),
    ("discovering", "scraping"),
    ("scraping", "enriching"),
    ("enriching", "selecting_media"),
    ("selecting_media", "generating"),
    ("generating", "validating"),
    ("validating", "ready_for_review"),
    ("ready_for_review", "approved"),
    ("approved", "deploying"),
    ("deploying", "deployed"),
)

OPERATIONAL_STATUSES = frozenset(
    {
        "queued",
        "discovering",
        "needs_social_review",
        "scraping",
        "enriching",
        "selecting_media",
        "generating",
        "validating",
        "deploying",
    }
)

AUTOMATED_ACTORS = frozenset({"pipeline", "cli"})

# Same-state pairs that CLI may repeat without appending history.
IDEMPOTENT_TRANSITIONS = frozenset({("queued", "queued")})


def _build_allowed() -> frozenset[tuple[str, str]]:
    allowed: set[tuple[str, str]] = set(HAPPY_PATH)
    allowed.add(("discovering", "needs_social_review"))
    allowed.add(("needs_social_review", "discovering"))
    allowed.add(("failed", "queued"))
    allowed.add(("ready_for_review", "rejected"))
    allowed.add(("rejected", "queued"))
    allowed.add(("approved", "ready_for_review"))
    allowed.add(("deploying", "approved"))
    for stage in OPERATIONAL_STATUSES:
        allowed.add((stage, "failed"))
    return frozenset(allowed)


ALLOWED_TRANSITIONS = _build_allowed()


def actor_base(actor: str) -> str:
    return actor.split(":", 1)[0]


def is_automated_actor(actor: str) -> bool:
    return actor_base(actor) in AUTOMATED_ACTORS


def is_allowed_transition(frm: str, to: str, actor: str) -> bool:
    if (frm, to) not in ALLOWED_TRANSITIONS:
        return False
    if frm == "ready_for_review" and to == "approved" and is_automated_actor(actor):
        return False
    return True


def assert_transition(frm: str, to: str, actor: str) -> None:
    if (frm, to) in IDEMPOTENT_TRANSITIONS:
        return
    if is_allowed_transition(frm, to, actor):
        return
    if frm == "ready_for_review" and to == "approved" and is_automated_actor(actor):
        raise PipelineError(
            INPUT_INVALID,
            "ready_for_review -> approved requires a human actor; "
            f"{actor!r} cannot auto-approve",
        )
    raise PipelineError(
        INPUT_INVALID,
        f"forbidden transition {frm} -> {to}",
    )
