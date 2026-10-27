import asyncio

from app.agents.runtime import MockAgentRuntime
from app.config import Settings
from app.models import SiteSnapshot
from app.pull_workflow import PullPlanningWorkflow


def test_three_page_mock_build_plan_preflight_without_openai():
    supported = [
        'get-site-snapshot', 'elementor-ensure-draft-page', 'set-page-seo',
        'ensure-approved-plugin', 'ensure-approved-theme', 'apply-site-design',
        'update-site-identity', 'ensure-navigation-menu', 'set-homepage-by-slug',
        'ensure-contact-form', 'configure-woocommerce', 'apply-acf-model'
    ]
    snapshot = SiteSnapshot(
        site_info={'bridge_version': '0.8.1', 'theme_slug': 'hello-elementor'},
        bridge_contract={'abilities': supported, 'action_journal_version': 1,
            'action_schema_version': 1, 'plugin_management_enabled': True,
            'filesystem_method': 'direct'},
        plugins=[{'slug': 'elementor', 'active': True}, {'slug': 'contact-form-7', 'active': True}],
        structure={'active_theme_slug': 'hello-elementor'},
        capabilities={'recognized_capabilities': {'page_builder_elementor': True,
            'forms': True}}
    )
    result = asyncio.run(PullPlanningWorkflow(
        Settings(agent_mode='mock', auto_approve_medium_risk=True), MockAgentRuntime()
    ).plan('Створи невеликий сайт стоматології: Головна, Послуги, Контакти', 'elementor', snapshot))
    approved = result['approved_actions']
    assert approved
    assert not result['blocked_actions'], result['blocked_actions']
    assert sum(a['action']['ability'] == 'thesis-ai-bridge/elementor-ensure-draft-page' for a in approved) >= 3
    assert not any(a['action']['ability'] == 'thesis-ai-bridge/ensure-approved-plugin' for a in approved)
    assert result['usage']['requests'] == 0
