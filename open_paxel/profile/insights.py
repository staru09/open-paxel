from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from open_paxel.models.domain import InsightCard, SessionReport

ARCHETYPE_NARRATIVES: dict[str, str] = {
    "Architect": "You plan first, codify decisions, and build scaffolding that compounds.",
    "Quality Guardian": "You push for tests, edge cases, and polish before calling work done.",
    "Velocity Machine": "You optimize for shipping — short loops, fast iteration, tangible output.",
    "Night Owl": "Your deepest work tends to land when most people have logged off.",
    "Explorer": "You learn by probing, asking questions, and following curiosity threads.",
    "Delegator": "You set direction and let the agent run, stepping in only when needed.",
}

WIDE_CARD_IDS = frozenset({"relationship", "crash", "shipped"})


@dataclass
class ProfileSignals:
    session_count: int = 0
    archetypes: Counter[str] = field(default_factory=Counter)
    model_counts: Counter[str] = field(default_factory=Counter)
    hour_hist: Counter[int] = field(default_factory=Counter)
    weekday_hist: Counter[str] = field(default_factory=Counter)
    phrase_totals: Counter[str] = field(default_factory=Counter)
    phrase_sessions: Counter[str] = field(default_factory=Counter)
    thank_you_total: int = 0
    redirect_hits: int = 0
    turn_total: int = 0
    short_prompt_sessions: int = 0
    max_agent_runs: int = 0
    max_agent_duration_ms: int = 0
    lines_added_total: int = 0
    cryptic: str | None = None
    crash: str | None = None
    relationship: str | None = None


def collect_profile_signals(reports: list[SessionReport]) -> ProfileSignals:
    signals = ProfileSignals(session_count=len(reports))

    for report in reports:
        signals.archetypes[report.archetype] += 1
        signals.weekday_hist[report.analyzed_at.strftime("%A")] += 1

        hm = report.heuristic_metrics
        if not hm:
            continue

        if hm.primary_model:
            signals.model_counts[hm.primary_model] += 1
        for hour, count in hm.hour_histogram.items():
            signals.hour_hist[hour] += count
        if hm.short_prompt_ratio >= 0.5:
            signals.short_prompt_sessions += 1

        signals.thank_you_total += hm.thank_you_count
        signals.redirect_hits += hm.redirect_hits
        signals.turn_total += hm.raw_turn_count or 1
        signals.max_agent_runs = max(signals.max_agent_runs, hm.agent_runs)
        signals.max_agent_duration_ms = max(signals.max_agent_duration_ms, hm.max_agent_duration_ms)
        signals.lines_added_total += hm.lines_added

        if hm.top_phrases:
            top_phrase = hm.top_phrases[0][0]
            signals.phrase_sessions[top_phrase] += 1
            for phrase, count in hm.top_phrases:
                signals.phrase_totals[phrase] += count

        ic = report.insight_candidates or {}
        signals.cryptic = signals.cryptic or ic.get("cryptic_prompt")
        signals.crash = signals.crash or ic.get("crash_out")
        signals.relationship = signals.relationship or ic.get("agent_relationship")

    return signals


def _fmt_duration(ms: int) -> str:
    total_seconds = max(ms // 1000, 0)
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _the_archetype(name: str) -> str:
    return name if name.lower().startswith("the ") else f"The {name}"


def _archetype_narrative(name: str) -> str:
    return ARCHETYPE_NARRATIVES.get(name, "Your sessions show a distinct builder pattern worth leaning into.")


def _night_share(hour_hist: Counter[int]) -> float:
    if not hour_hist:
        return 0.0
    night = sum(hour_hist[h] for h in hour_hist if h >= 22 or h < 6)
    return night / sum(hour_hist.values())


def _morning_share(hour_hist: Counter[int]) -> float:
    if not hour_hist:
        return 0.0
    morning = sum(hour_hist.get(h, 0) for h in range(6, 12))
    return morning / sum(hour_hist.values())


def _peak_hour_label(hour_hist: Counter[int]) -> str | None:
    if not hour_hist:
        return None
    peak = max(hour_hist, key=hour_hist.get)
    if peak == 0:
        return "midnight"
    if peak < 12:
        return f"{peak} AM"
    if peak == 12:
        return "noon"
    return f"{peak - 12} PM"


def build_insight_cards(
    signals: ProfileSignals,
    *,
    decision_stats: dict[str, object] | None = None,
) -> list[InsightCard]:
    if signals.session_count == 0:
        return []

    cards: list[InsightCard] = []
    n = signals.session_count

    top_archetype = signals.archetypes.most_common(1)[0][0]
    cards.append(
        InsightCard(
            id="archetype",
            question="Which archetype are you?",
            title="Archetype",
            value=_the_archetype(top_archetype),
            subtitle=_archetype_narrative(top_archetype),
        )
    )

    if signals.model_counts:
        top_model, count = signals.model_counts.most_common(1)[0]
        pct = round(100 * count / n)
        runner_up = ""
        if len(signals.model_counts) > 1:
            second_model, second_count = signals.model_counts.most_common(2)[1]
            second_pct = round(100 * second_count / n)
            runner_up = f", {second_model} {second_pct}%"
        cards.append(
            InsightCard(
                id="model",
                question="Which model do you use most?",
                title="Top model",
                value=f"You reach for {top_model}",
                subtitle=f"Used in {count} of {n} sessions ({pct}%){runner_up}.",
            )
        )

    night_pct = round(_night_share(signals.hour_hist) * 100)
    morning_pct = round(_morning_share(signals.hour_hist) * 100)
    peak = _peak_hour_label(signals.hour_hist)
    if night_pct >= 40:
        cards.append(
            InsightCard(
                id="productivity",
                question="When are you most productive?",
                title="Productivity",
                value="Night owl",
                subtitle=f"{night_pct}% of your prompts land between 10 PM and 6 AM"
                + (f", peaking around {peak}." if peak else "."),
            )
        )
    elif morning_pct >= 50:
        cards.append(
            InsightCard(
                id="productivity",
                question="When are you most productive?",
                title="Productivity",
                value="Early bird",
                subtitle=f"{morning_pct}% of your activity shows up before noon.",
            )
        )

    if signals.phrase_totals:
        phrase, hits = signals.phrase_totals.most_common(1)[0]
        session_hits = signals.phrase_sessions.get(phrase, 1)
        cards.append(
            InsightCard(
                id="goto",
                question="What's your go-to prompt?",
                title="Go-to phrase",
                value=phrase,
                subtitle=f"Your most-used phrase, appearing {hits} times across {session_hits} session(s).",
            )
        )

    if signals.max_agent_runs >= 2:
        cards.append(
            InsightCard(
                id="agents",
                question="How many agents do you run?",
                title="Parallel agents",
                value=f"Up to {signals.max_agent_runs} agents",
                subtitle=f"You've run as many as {signals.max_agent_runs} coding agents in a single session.",
            )
        )

    short_pct = round(100 * signals.short_prompt_sessions / n)
    if short_pct >= 50:
        cards.append(
            InsightCard(
                id="prompts",
                question="How long are your prompts?",
                title="Prompt style",
                value="Straight to the point",
                subtitle=f"{short_pct}% of your sessions skew toward prompts under 10 words.",
            )
        )
    elif short_pct <= 25 and n >= 1:
        cards.append(
            InsightCard(
                id="prompts",
                question="How long are your prompts?",
                title="Prompt style",
                value="Detailed",
                subtitle="You tend to front-load context and explain the full picture before asking for work.",
            )
        )

    if signals.cryptic:
        cards.append(
            InsightCard(
                id="cryptic",
                question="Your most cryptic prompt?",
                title="Cryptic prompt",
                value=signals.cryptic[:120],
                subtitle="A memorable low-context prompt the agent still had to interpret.",
            )
        )

    if signals.thank_you_total >= 2:
        cards.append(
            InsightCard(
                id="thanks",
                question="How polite are you to your agent?",
                title="Politeness",
                value="You thank your agent",
                subtitle=f"You said thanks {signals.thank_you_total} times across your sessions.",
            )
        )

    redirects_per_10 = (signals.redirect_hits / max(signals.turn_total, 1)) * 10
    if redirects_per_10 >= 2.5:
        cards.append(
            InsightCard(
                id="steering",
                question="How often do you change course?",
                title="Steering",
                value="You steer, hard",
                subtitle=f"You redirect mid-task roughly {redirects_per_10:.0f} times per 10 turns.",
            )
        )

    if signals.max_agent_duration_ms >= 15 * 60 * 1000:
        cards.append(
            InsightCard(
                id="longest_run",
                question="What's your longest agent run?",
                title="Longest run",
                value=_fmt_duration(signals.max_agent_duration_ms),
                subtitle="One agent kept going on a single task before you stepped back in.",
            )
        )

    if signals.crash:
        cards.append(
            InsightCard(
                id="crash",
                question="What's your biggest crash out?",
                title="Crash out",
                value=signals.crash[:120],
                subtitle="When frustration peaked, your prompts got louder and more direct.",
            )
        )

    if signals.lines_added_total >= 50:
        cards.append(
            InsightCard(
                id="shipped",
                question="How much did you ship?",
                title="Output",
                value=f"{signals.lines_added_total:,} lines added",
                subtitle=f"Across {n} analyzed session(s) with measurable code output.",
            )
        )

    if signals.relationship:
        cards.append(
            InsightCard(
                id="relationship",
                question="How do you see your agent?",
                title="Agent relationship",
                value="Like a collaborator",
                subtitle=signals.relationship,
            )
        )

    if n >= 2 and signals.weekday_hist:
        ship_day, ship_count = signals.weekday_hist.most_common(1)[0]
        if ship_count >= 2:
            cards.append(
                InsightCard(
                    id="ship_day",
                    question="When do you ship most?",
                    title="Ship rhythm",
                    value=ship_day + "s",
                    subtitle=f"Your heaviest analysis activity clusters on {ship_day}s ({ship_count} sessions).",
                )
            )

    if decision_stats:
        top_title = decision_stats.get("top_catalog_title")
        total = decision_stats.get("total", 0)
        by_catalog = decision_stats.get("by_catalog_key") or {}
        if top_title and isinstance(by_catalog, dict) and total:
            top_key = decision_stats.get("top_catalog_key")
            count = by_catalog.get(top_key, 0) if top_key else 0
            cards.append(
                InsightCard(
                    id="decision_pattern",
                    question="Which decision pattern shows up most?",
                    title="Matched pattern",
                    value=str(top_title),
                    subtitle=f"Appeared in {count} of {total} tracked decision(s).",
                )
            )

    return cards


def is_wide_card(card: InsightCard) -> bool:
    return card.id in WIDE_CARD_IDS or len(card.subtitle or "") > 120
