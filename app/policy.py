from __future__ import annotations

from dataclasses import dataclass

from .models import AgentRole, BuildAction, PolicyDecision, PolicyOutcome, RiskLevel


@dataclass(frozen=True)
class Rule:
    risk: RiskLevel
    allowed_roles: frozenset[AgentRole]
    approval_required: bool = False
    blocked: bool = False


class PolicyEngine:
    """Deterministic safety gate. This is intentionally NOT an LLM agent."""

    APPROVED_PLUGINS = {
        "elementor",
        "woocommerce",
        "advanced-custom-fields",
        "contact-form-7",
        "wordpress-seo",
        "seo-by-rank-math",
    }

    RULES: dict[str, Rule] = {
        "thesis-ai-bridge/get-site-info": Rule(RiskLevel.LOW, frozenset({AgentRole.ARCHITECT, AgentRole.BUILDER, AgentRole.QUALITY})),
        "thesis-ai-bridge/list-pages": Rule(RiskLevel.LOW, frozenset({AgentRole.ARCHITECT, AgentRole.BUILDER, AgentRole.QUALITY})),
        "thesis-ai-bridge/get-page": Rule(RiskLevel.LOW, frozenset({AgentRole.ARCHITECT, AgentRole.BUILDER, AgentRole.QUALITY})),
        "thesis-ai-bridge/list-plugins": Rule(RiskLevel.LOW, frozenset({AgentRole.ARCHITECT, AgentRole.BUILDER, AgentRole.QUALITY})),
        "thesis-ai-bridge/inspect-capabilities": Rule(RiskLevel.LOW, frozenset({AgentRole.ARCHITECT, AgentRole.BUILDER, AgentRole.QUALITY})),
        "thesis-ai-bridge/get-approved-plugin-info": Rule(RiskLevel.LOW, frozenset({AgentRole.ARCHITECT, AgentRole.BUILDER})),
        "thesis-ai-bridge/elementor-get-status": Rule(RiskLevel.LOW, frozenset({AgentRole.ARCHITECT, AgentRole.BUILDER, AgentRole.QUALITY})),
        "thesis-ai-bridge/elementor-get-page": Rule(RiskLevel.LOW, frozenset({AgentRole.ARCHITECT, AgentRole.BUILDER, AgentRole.QUALITY})),
        "thesis-ai-bridge/create-draft-page": Rule(RiskLevel.LOW, frozenset({AgentRole.BUILDER})),
        "thesis-ai-bridge/ensure-draft-page": Rule(RiskLevel.LOW, frozenset({AgentRole.BUILDER})),
        "thesis-ai-bridge/elementor-ensure-draft-page": Rule(RiskLevel.LOW, frozenset({AgentRole.BUILDER})),
        "thesis-ai-bridge/update-page": Rule(RiskLevel.MEDIUM, frozenset({AgentRole.BUILDER})),
        "thesis-ai-bridge/set-homepage": Rule(RiskLevel.MEDIUM, frozenset({AgentRole.BUILDER})),
        "thesis-ai-bridge/install-approved-plugin": Rule(RiskLevel.MEDIUM, frozenset({AgentRole.BUILDER})),
        "thesis-ai-bridge/activate-approved-plugin": Rule(RiskLevel.MEDIUM, frozenset({AgentRole.BUILDER})),
        "thesis-ai-bridge/deactivate-approved-plugin": Rule(RiskLevel.MEDIUM, frozenset({AgentRole.BUILDER})),
        "thesis-ai-bridge/ensure-approved-plugin": Rule(RiskLevel.MEDIUM, frozenset({AgentRole.BUILDER})),
        "acf.apply-model": Rule(RiskLevel.MEDIUM, frozenset({AgentRole.BUILDER})),
        "woocommerce.configure": Rule(RiskLevel.MEDIUM, frozenset({AgentRole.BUILDER})),
        "snippets.execute-php": Rule(RiskLevel.HIGH, frozenset({AgentRole.BUILDER}), approval_required=True),
        "raw-sql.execute": Rule(RiskLevel.CRITICAL, frozenset(), blocked=True),
        "filesystem.write": Rule(RiskLevel.CRITICAL, frozenset(), blocked=True),
        "auth.change": Rule(RiskLevel.CRITICAL, frozenset(), blocked=True),
        "shell.execute": Rule(RiskLevel.CRITICAL, frozenset(), blocked=True),
    }

    def evaluate(self, actor: AgentRole, action: BuildAction, auto_approve_medium: bool = True) -> PolicyDecision:
        rule = self.RULES.get(action.ability)
        if rule is None:
            return PolicyDecision(ability=action.ability, risk=RiskLevel.HIGH, outcome=PolicyOutcome.BLOCK, reason="Unknown ability: default deny.")
        if rule.blocked:
            return PolicyDecision(ability=action.ability, risk=rule.risk, outcome=PolicyOutcome.BLOCK, reason="Ability is forbidden by policy.")
        if actor not in rule.allowed_roles:
            return PolicyDecision(ability=action.ability, risk=rule.risk, outcome=PolicyOutcome.BLOCK, reason=f"Role {actor.value} is not allowed to execute this ability.")

        if action.ability in {
            "thesis-ai-bridge/install-approved-plugin",
            "thesis-ai-bridge/activate-approved-plugin",
            "thesis-ai-bridge/deactivate-approved-plugin",
            "thesis-ai-bridge/ensure-approved-plugin",
            "thesis-ai-bridge/get-approved-plugin-info",
        }:
            slug = str(action.parameters.get("plugin_slug", ""))
            if slug not in self.APPROVED_PLUGINS:
                return PolicyDecision(ability=action.ability, risk=RiskLevel.HIGH, outcome=PolicyOutcome.BLOCK, reason=f"Plugin '{slug}' is not in the approved catalogue.")

        if rule.approval_required:
            return PolicyDecision(ability=action.ability, risk=rule.risk, outcome=PolicyOutcome.REQUIRE_APPROVAL, reason="High-risk operation requires explicit human approval.")
        if rule.risk == RiskLevel.MEDIUM and not auto_approve_medium:
            return PolicyDecision(ability=action.ability, risk=rule.risk, outcome=PolicyOutcome.REQUIRE_APPROVAL, reason="Medium-risk auto-approval is disabled.")
        return PolicyDecision(ability=action.ability, risk=rule.risk, outcome=PolicyOutcome.ALLOW, reason="Action satisfies the deterministic policy rules.")
