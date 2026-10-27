from pathlib import Path

import pytest

from app.action_validation import validate_action
from app.connection_token import ConnectionTokenCodec
from app.repository import JobRepository
from app.models import BuildAction, AgentRole, PolicyOutcome
from app.policy import PolicyEngine


def make_repo(path):
    return JobRepository(f"sqlite:///{path}")


def test_job_persists_across_repository_restart(tmp_path: Path):
    file = tmp_path / "jobs.sqlite3"
    a = make_repo(file)
    job = {"job_id": "abc", "site_id": "s1", "status": "queued", "_payload": {"request": "long enough test prompt"}, "progress": 0}
    a.put(job)
    a.close()
    b = make_repo(file)
    assert b.get("abc", "s1") == job
    assert b.active("s1") == job
    assert b.get("abc", "s2") is None
    b.put(dict(job, status="completed", progress=100))
    assert b.active("s1") is None
    assert b.get("abc", "s1")["progress"] == 100
    b.close()


def test_revoke_site_survives_restart(tmp_path: Path):
    path = tmp_path / "jobs.sqlite3"
    first = make_repo(path)
    assert not first.is_revoked("test-site")
    first.revoke_site("test-site")
    first.close()
    second = make_repo(path)
    assert second.is_revoked("test-site")
    second.close()


def test_no_wordpress_password_in_new_tokens(tmp_path: Path):
    codec = ConnectionTokenCodec("secret", tmp_path / "key")
    site_id, token = codec.issue(site_url="https://test.example", username="admin", application_password="never-store-me", bridge_version="0.8.1", site_name="Site")
    decoded = codec.decode(site_id, token)
    assert decoded is not None
    assert decoded.username == ""
    assert decoded.application_password == ""


def test_action_params_fail_closed():
    action = BuildAction(ability="thesis-ai-bridge/set-homepage-by-slug", parameters={"slug": "../wp-config.php"}, rationale="bad")
    assert PolicyEngine().evaluate(AgentRole.BUILDER, action).outcome == PolicyOutcome.BLOCK
    plugin = BuildAction(ability="thesis-ai-bridge/ensure-approved-plugin", parameters={"plugin_slug": "elementor", "backdoor": "yes"}, rationale="bad")
    assert PolicyEngine().evaluate(AgentRole.BUILDER, plugin).outcome == PolicyOutcome.BLOCK
    assert validate_action("thesis-ai-bridge/apply-site-design", {"primary": "javascript:evil"})


def test_normal_valid_params_are_allowed():
    action = BuildAction(ability="thesis-ai-bridge/set-homepage-by-slug", parameters={"slug": "home"}, rationale="ok")
    assert PolicyEngine().evaluate(AgentRole.BUILDER, action).outcome == PolicyOutcome.ALLOW
    assert validate_action("thesis-ai-bridge/ensure-approved-plugin", {"plugin_slug": "elementor"}) is None


def test_old_contract_rejected_without_model_calls():
    from app.pull_workflow import PullPlanningWorkflow
    from app.models import SiteSnapshot
    complete = ["get-site-snapshot", "set-page-seo", "apply-site-design", "ensure-navigation-menu", "set-homepage-by-slug", "update-site-identity", "elementor-ensure-draft-page"]
    old = SiteSnapshot(site_info={"bridge_version": "0.8.0"}, bridge_contract={"abilities": complete})
    with pytest.raises(RuntimeError, match="action journal"):
        PullPlanningWorkflow._validate_bridge_contract(old, "elementor")
    modern = SiteSnapshot(site_info={"bridge_version": "0.8.1"}, bridge_contract={"abilities": complete, "action_journal_version": 1, "action_schema_version": 1})
    PullPlanningWorkflow._validate_bridge_contract(modern, "elementor")
