from __future__ import annotations

import re
from collections import Counter

from open_paxel.models.domain import HeuristicMetrics, SessionFacts

STOPWORDS = {
    "a", "an", "the", "to", "in", "on", "for", "of", "and", "or", "is", "it",
    "this", "that", "with", "my", "me", "i", "you", "can", "please", "just",
}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _phrase_counts(messages: list) -> list[tuple[str, int]]:
    phrases: Counter[str] = Counter()
    for msg in messages:
        words = re.findall(r"[a-zA-Z']+", msg.text.lower())
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                gram = tuple(words[i : i + n])
                if any(w in STOPWORDS for w in gram):
                    continue
                phrases[" ".join(gram)] += 1
    return phrases.most_common(5)


def _productivity_label(hour_hist: dict[int, int]) -> str | None:
    if not hour_hist:
        return None
    night = sum(hour_hist.get(h, 0) for h in range(22, 24)) + sum(
        hour_hist.get(h, 0) for h in range(0, 6)
    )
    total = sum(hour_hist.values())
    if total and night / total >= 0.5:
        return "Night owl"
    morning = sum(hour_hist.get(h, 0) for h in range(6, 12))
    if total and morning / total >= 0.5:
        return "Early bird"
    return "Flexible"


def _effective_turns(facts: SessionFacts) -> int:
    if facts.raw_turn_count:
        return max(facts.raw_turn_count, 1)
    if facts.total_tokens:
        return max(1, facts.total_tokens // 350)
    return max(len(facts.user_messages), 1)


def compute_heuristics(facts: SessionFacts) -> HeuristicMetrics:
    turns = _effective_turns(facts)
    total_tokens = max(facts.total_tokens, 1)

    redirect_rate = facts.redirect_hits / turns

    # Token-normalized steering: more redirects per 1k tokens = higher steering
    redirects_per_1k = (facts.redirect_hits / total_tokens) * 1000
    steering = _clamp(
        25
        + redirect_rate * 100
        + redirects_per_1k * 8
        + min(len(facts.user_messages) * 2, 25)
    )

    code_blocks = facts.tool_counts.get("CodeBlock", 0)
    write_tools = facts.tool_counts.get("Write", 0)
    code_tokens_est = code_blocks * 120
    code_density = min(1.0, code_tokens_est / total_tokens) if total_tokens else 0

    code_score = (
        facts.lines_added * 0.05
        + facts.files_edited * 6
        + write_tools * 5
        + code_blocks * 4
        + code_density * 40
    )
    execution = _clamp(min(code_score, 100))

    error_penalty = min(facts.tool_errors * 6, 35)
    test_bonus = min(facts.test_lint_runs * 10, 30)
    test_density = (facts.test_lint_runs / max(total_tokens / 2000, 1)) * 15
    engineering = _clamp(45 - error_penalty + test_bonus + test_density)

    explore = facts.question_prompts / turns
    questions_per_1k = (facts.question_prompts / total_tokens) * 1000
    read_tools = facts.tool_counts.get("Read", 0) + facts.tool_counts.get("Grep", 0)
    product = _clamp(
        20 + explore * 70 + questions_per_1k * 5 + min(read_tools * 2, 20)
    )

    plan_used = facts.plan_mode_entries > 0
    plan_score = facts.plan_mode_entries * 15 + (20 if plan_used else 0)
    word_counts = [m.word_count for m in facts.user_messages] or [0]
    avg_words = sum(word_counts) / len(word_counts)
    short_ratio = sum(1 for w in word_counts if w <= 10) / len(word_counts)
    long_segments = sum(1 for w in word_counts if w > 80) / len(word_counts)
    planning = _clamp(plan_score + long_segments * 35 + (1 - short_ratio) * 15)

    model_dist: dict[str, int] = {}
    for m in facts.models_used:
        model_dist[m] = model_dist.get(m, 0) + 1
    primary_model = max(model_dist, key=model_dist.get) if model_dist else None

    hour_hist: dict[int, int] = {}
    for msg in facts.user_messages:
        if msg.timestamp:
            h = msg.timestamp.hour
            hour_hist[h] = hour_hist.get(h, 0) + 1
    peak_hour = max(hour_hist, key=hour_hist.get) if hour_hist else None

    return HeuristicMetrics(
        steering=steering,
        execution=execution,
        engineering=engineering,
        product_instinct=product,
        planning=planning,
        redirect_rate=redirect_rate,
        plan_mode_used=plan_used,
        avg_prompt_words=avg_words,
        short_prompt_ratio=short_ratio,
        top_phrases=_phrase_counts(facts.user_messages),
        primary_model=primary_model,
        model_distribution=model_dist,
        hour_histogram=hour_hist,
        peak_hour=peak_hour,
        productivity_label=_productivity_label(hour_hist),
        thank_you_count=facts.thank_you_count,
        agent_runs=facts.agent_runs,
        max_agent_duration_ms=facts.max_agent_duration_ms,
        lines_added=facts.lines_added,
        redirect_hits=facts.redirect_hits,
        raw_turn_count=facts.raw_turn_count or len(facts.user_messages),
    )


def blend_dimension(heuristic: float, llm_score: float, heuristic_weight: float = 0.4) -> float:
    return round(heuristic * heuristic_weight + llm_score * (1 - heuristic_weight), 1)
