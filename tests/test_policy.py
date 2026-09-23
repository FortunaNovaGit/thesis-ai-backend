from app.models import AgentRole, BuildAction, PolicyOutcome, RiskLevel
from app.policy import PolicyEngine


def test_builder_can_ensure_draft_page():
    decision = PolicyEngine().evaluate(
        AgentRole.BUILDER,
        BuildAction(ability="thesis-ai-bridge/ensure-draft-page", parameters={"title": "Home", "slug": "home"}, rationale="test"),
    )
    assert decision.outcome == PolicyOutcome.ALLOW
    assert decision.risk == RiskLevel.LOW


def test_unknown_ability_is_default_deny():
    decision = PolicyEngine().evaluate(
        AgentRole.BUILDER,
        BuildAction(ability="unknown.do-anything", rationale="test"),
    )
    assert decision.outcome == PolicyOutcome.BLOCK


def test_raw_sql_is_blocked():
    decision = PolicyEngine().evaluate(
        AgentRole.BUILDER,
        BuildAction(ability="raw-sql.execute", parameters={"sql": "DELETE FROM wp_posts"}, rationale="test"),
    )
    assert decision.outcome == PolicyOutcome.BLOCK
    assert decision.risk == RiskLevel.CRITICAL


def test_unapproved_plugin_is_blocked():
    decision = PolicyEngine().evaluate(
        AgentRole.BUILDER,
        BuildAction(
            ability="thesis-ai-bridge/install-approved-plugin",
            parameters={"plugin_slug": "random-plugin"},
            rationale="test",
        ),
    )
    assert decision.outcome == PolicyOutcome.BLOCK


def test_approved_plugin_is_medium_risk():
    decision = PolicyEngine().evaluate(
        AgentRole.BUILDER,
        BuildAction(
            ability="thesis-ai-bridge/install-approved-plugin",
            parameters={"plugin_slug": "woocommerce"},
            rationale="test",
        ),
        auto_approve_medium=False,
    )
    assert decision.outcome == PolicyOutcome.REQUIRE_APPROVAL
    assert decision.risk == RiskLevel.MEDIUM
