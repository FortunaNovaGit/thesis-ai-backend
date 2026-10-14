from __future__ import annotations

from dataclasses import dataclass

from .models import AgentCallUsage, AgentUsage, BudgetState


# Public list pricing reference as of 2026-10-14. Values are USD per 1M text
# tokens and are deliberately used only for an *estimate*, not billing authority.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.6-sol": (4.00, 20.00),
    "gpt-5.6": (4.00, 20.00),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_rate, output_rate = MODEL_PRICING.get(model, MODEL_PRICING["gpt-5.6-terra"])
    return round((input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate, 6)


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class BudgetLimits:
    max_cost_usd: float
    max_total_tokens: int
    max_llm_calls: int


class BudgetTracker:
    def __init__(self, limits: BudgetLimits) -> None:
        self.limits = limits
        self.usage = AgentUsage()

    def assert_can_call(self) -> None:
        if self.usage.requests >= self.limits.max_llm_calls:
            raise BudgetExceeded(f"LLM call budget reached ({self.usage.requests}/{self.limits.max_llm_calls}).")
        if self.usage.total_tokens >= self.limits.max_total_tokens:
            raise BudgetExceeded(f"Token budget reached ({self.usage.total_tokens}/{self.limits.max_total_tokens}).")
        if self.usage.estimated_cost_usd >= self.limits.max_cost_usd:
            raise BudgetExceeded(
                f"Estimated API budget reached (${self.usage.estimated_cost_usd:.3f}/${self.limits.max_cost_usd:.3f})."
            )

    def record(self, agent: str, model: str, requests: int, input_tokens: int, output_tokens: int) -> None:
        total_tokens = input_tokens + output_tokens
        cost = estimate_cost(model, input_tokens, output_tokens)
        call = AgentCallUsage(
            agent=agent,
            model=model,
            requests=max(1, requests),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
        )
        delta = AgentUsage(
            requests=max(1, requests),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
            calls=[call],
        )
        self.usage.add(delta)
        if self.usage.total_tokens > self.limits.max_total_tokens:
            raise BudgetExceeded(
                f"Token budget exceeded after {agent}: {self.usage.total_tokens}/{self.limits.max_total_tokens}."
            )
        if self.usage.estimated_cost_usd > self.limits.max_cost_usd:
            raise BudgetExceeded(
                f"Estimated API budget exceeded after {agent}: ${self.usage.estimated_cost_usd:.3f}/${self.limits.max_cost_usd:.3f}."
            )

    def state(self) -> BudgetState:
        return BudgetState(
            max_cost_usd=self.limits.max_cost_usd,
            max_total_tokens=self.limits.max_total_tokens,
            max_llm_calls=self.limits.max_llm_calls,
            used_cost_usd=self.usage.estimated_cost_usd,
            used_total_tokens=self.usage.total_tokens,
            used_llm_calls=self.usage.requests,
            remaining_cost_usd=max(0.0, round(self.limits.max_cost_usd - self.usage.estimated_cost_usd, 6)),
            remaining_tokens=max(0, self.limits.max_total_tokens - self.usage.total_tokens),
            remaining_calls=max(0, self.limits.max_llm_calls - self.usage.requests),
        )
