from __future__ import annotations

from collections import Counter

from open_paxel.models.domain import SessionReport
from open_paxel.models.pipeline_models import Episode
from open_paxel.models.profile_narrative import ProfileNarrative
from open_paxel.profile.insights import ProfileSignals, _the_archetype


def _session_phrase(n: int, word: str = "session") -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _format_exchange_stats(stats: dict[str, object]) -> str:
    by_type = stats.get("by_exchange_type") or {}
    if not isinstance(by_type, dict) or not by_type:
        return ""
    total = stats.get("total", 0)
    parts = [f"{count} {label.replace('_', ' ')}" for label, count in by_type.items()]
    arch = by_type.get("strategic_redirect", 0) + by_type.get("technical_catch", 0)
    intro = "Your decision style is architecture-heavy." if arch >= (total or 0) / 2 else (
        "Your decision style balances exploration with targeted corrections."
    )
    return f"{intro} Across {total} tracked decision(s): " + ", ".join(parts) + "."


def build_profile_narrative(
    reports: list[SessionReport],
    signals: ProfileSignals,
    *,
    archetype: str,
    signature_moves: list[str],
    growth_edge: list[str],
    decision_stats: dict[str, object] | None = None,
    episodes: list[Episode] | None = None,
) -> ProfileNarrative:
    if not reports:
        return ProfileNarrative()

    n = len(reports)
    top_arch = _the_archetype(archetype)
    decision_stats = decision_stats or {}

    narrative = (
        f"You used Claude Code as an implementation engine. "
        f"Across {_session_phrase(n)}, your builder pattern reads as {top_arch}."
    )

    built_parts: list[str] = []
    for report in reports[:5]:
        if report.session_narrative and report.session_narrative.what_was_built:
            built_parts.append(report.session_narrative.what_was_built)
        elif report.title:
            built_parts.append(report.title)
    if episodes:
        for ep in episodes:
            if not ep.skipped and ep.title:
                built_parts.append(ep.title)
    what_you_built = " ".join(dict.fromkeys(built_parts)) or (
        "Your analyzed sessions show sustained building work with Claude Code."
    )

    decision_patterns = _format_exchange_stats(decision_stats)
    if not decision_patterns and signature_moves:
        decision_patterns = f"Recurring moves include: {signature_moves[0]}."

    matched = decision_stats.get("top_catalog_title")
    matched_category = decision_stats.get("top_catalog_category")
    if not matched and signature_moves:
        matched = signature_moves[0]
        matched_category = "Code & Architecture"

    strengths: list[str] = []
    catalog_counts = decision_stats.get("by_catalog_key") or {}
    if isinstance(catalog_counts, dict):
        for key, count in Counter(catalog_counts).most_common(3):
            title = key.replace("-", " ").title()
            strengths.append(
                f"In {_session_phrase(n)}, you showed {title} ({count} decision(s))."
            )
    for move in signature_moves[:2]:
        if len(strengths) >= 4:
            break
        strengths.append(f"In {_session_phrase(n)}, {move[0].lower() + move[1:] if move else move}.")

    growth_areas: list[str] = list(growth_edge[:3])
    planning_scores = [r.dimensions["planning"].score for r in reports if "planning" in r.dimensions]
    if planning_scores and sum(planning_scores) / len(planning_scores) < 55 and len(growth_areas) < 3:
        growth_areas.append(
            f"In {_session_phrase(n)}, planning signals were light. "
            "Before the next long run, write a short plan with target files, expected outputs, and validation steps."
        )

    return ProfileNarrative(
        narrative=narrative,
        what_you_built=what_you_built,
        decision_patterns=decision_patterns.strip(),
        matched_pattern=str(matched) if matched else None,
        matched_pattern_category=str(matched_category) if matched_category else None,
        strengths=strengths[:4],
        growth_areas=growth_areas[:3],
    )
