import asyncio
import json

from app import api
from app.action_validation import validate_action
from app.agents.runtime import MockAgentRuntime, explicitly_named_demo_products
from app.models import SiteSnapshot
from app.pull_workflow import PullPlanningWorkflow
from app.config import Settings
from app.policy import PolicyEngine
from app.models import AgentRole, BuildAction


def test_products_require_explicit_quoted_names_and_ignore_brand():
    text = 'Інтернет магазин «Fortuna Nova»: товари «Асорті 16 цукерок» та «Асорті 24 цукерки». Не вигадуй ціни.'
    assert explicitly_named_demo_products(text) == ['Асорті 16 цукерок', 'Асорті 24 цукерки']
    assert explicitly_named_demo_products('Зроби магазин шоколаду без назв товарів') == []
    assert explicitly_named_demo_products('«Асорті 16 цукерок» «Асорті 16 цукерок»') == ['Асорті 16 цукерок']


def test_product_action_validation_and_policy():
    action = BuildAction(ability='thesis-ai-bridge/ensure-woocommerce-product-draft',
                         parameters={'name': 'Асорті 16 цукерок', 'description': 'Неопублікований демо набір без ціни'},
                         rationale='Explicitly requested')
    assert validate_action(action.ability, action.parameters) is None
    assert PolicyEngine().evaluate(AgentRole.BUILDER, action, auto_approve_medium=True).outcome.value == 'allow'
    assert validate_action(action.ability, {**action.parameters, 'price': '500'}) is not None
    assert validate_action(action.ability, {**action.parameters, 'status': 'publish'}) is not None


def test_ecommerce_plan_includes_only_explicit_product_drafts():
    supported = [
        'get-site-snapshot','elementor-ensure-draft-page','set-page-seo',
        'ensure-approved-plugin','ensure-approved-theme','apply-site-design',
        'update-site-identity','ensure-navigation-menu','set-homepage-by-slug',
        'ensure-contact-form','configure-woocommerce','apply-acf-model',
        'ensure-woocommerce-product-draft',
    ]
    snapshot = SiteSnapshot(
        site_info={'bridge_version': '0.8.2', 'theme_slug': 'hello-elementor'},
        bridge_contract={'abilities': supported, 'action_journal_version': 1,
            'action_schema_version': 1, 'plugin_management_enabled': True,
            'filesystem_method': 'direct'},
        plugins=[{'slug':'elementor','active':True}, {'slug':'woocommerce','active':True}],
        structure={'active_theme_slug':'hello-elementor'},
        capabilities={'recognized_capabilities': {'page_builder_elementor':True,'ecommerce':True}},
    )
    prompt = 'Створи магазин шоколадних цукерок, товари «Асорті 16 цукерок» і «Асорті 24 цукерки».'
    result = asyncio.run(PullPlanningWorkflow(Settings(agent_mode='mock'),MockAgentRuntime()).plan(prompt,'elementor',snapshot))
    assert not result['blocked_actions']
    actions = [x['action'] for x in result['approved_actions']]
    product_actions = [x for x in actions if x['ability']=='thesis-ai-bridge/ensure-woocommerce-product-draft']
    assert len(product_actions)==2
    assert {x['parameters']['name'] for x in product_actions} == {'Асорті 16 цукерок','Асорті 24 цукерки'}
    assert all('price' not in x['parameters'] and 'status' not in x['parameters'] for x in product_actions)
    assert actions.index(product_actions[0]) < next(i for i,a in enumerate(actions) if a['ability']=='thesis-ai-bridge/elementor-ensure-draft-page')
    assert result['usage']['requests']==0


def test_rehydrate_compact_execution_with_full_original_plan():
    big_json = {'elements':[{'id':str(i),'settings':{'body':'X'*5000}} for i in range(10)]}
    source = {'ability':'thesis-ai-bridge/elementor-ensure-draft-page', 'parameters':{'slug':'home', **big_json},'rationale':'create'}
    bundle={'approved_actions':[{'action':source,'policy':{'outcome':'allow'}}]}
    compact=[{'planned_action_index':0,'action':{'ability':source['ability'],'parameters':{'slug':'home'}},
              'executed':True,'result':{'id':100},'error':'','attempt':1}]
    restored=api._rehydrate_executions(compact,bundle)
    assert restored[0]['action']==source
    assert len(json.dumps(compact)) < 1000
    assert len(json.dumps(bundle)) > 45000


def test_verify_by_durable_plan_id_without_large_bundle(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.repository import JobRepository

    old_repo = api.repository
    repo = JobRepository(f'sqlite:///{tmp_path / "qa.db"}')
    monkeypatch.setattr(api, 'repository', repo)
    monkeypatch.setattr(api, '_credentials', lambda site_id, auth: {'site_id':site_id})
    monkeypatch.setattr(api.settings, 'agent_mode', 'mock')
    try:
        snapshot = SiteSnapshot()
        bundle = asyncio.run(PullPlanningWorkflow(
            Settings(agent_mode='mock'), MockAgentRuntime()
        ).plan('Зроби сайт стоматології з трьома сторінками та контактами', 'elementor', snapshot))
        # Huge plan is persisted once; WordPress POST verification needs only its ID.
        bundle['large_unrelated_preview_artifact'] = 'X'*950_000
        repo.put({'job_id':'job-one', 'site_id':'site-one', 'status':'completed','result':bundle})
        payload = {'plan_job_id':'job-one','executions':[],
                   'verification_snapshot':snapshot.model_dump(mode='json'), 'repair_attempts':1}
        assert len(json.dumps(payload)) < 1000
        with TestClient(api.app) as client:
            good = client.post('/v2/sites/site-one/verify', json=payload)
            assert good.status_code == 200, good.text
            assert 'quality_report' in good.json()
            bad = client.post('/v2/sites/another-site/verify', json=payload)
            assert bad.status_code == 409
    finally:
        repo.close()
        monkeypatch.setattr(api, 'repository', old_repo)
