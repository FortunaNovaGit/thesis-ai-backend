"""v0.11 opt-in image pipeline: offline tests, no paid API calls."""
import asyncio
import time
import uuid
from pathlib import Path
from fastapi.testclient import TestClient
from app import api
from app.agents.runtime import MockAgentRuntime
from app.config import Settings
from app.models import SiteSnapshot
from app.pull_workflow import PullPlanningWorkflow
from app.media_store import MediaStore
from app.media_pipeline import build_media_manifest
from app.component_library import compile_elementor_page
from app.repository import JobRepository
from test_v094_quality_first import walk


def sample_bundle():
    snapshot = SiteSnapshot(site_info={"theme_slug": "hello-elementor"},
        plugins=[{"slug":"elementor","active":True},{"slug":"woocommerce","active":True}],
        structure={"active_theme_slug":"hello-elementor"})
    prompt="Створи преміальний магазин шоколадних цукерок Fortuna Nova українською, головна, магазин, контакти"
    bundle=asyncio.run(PullPlanningWorkflow(Settings(agent_mode="mock"),MockAgentRuntime()).plan(prompt,"elementor",snapshot))
    return snapshot,bundle


def test_media_manifest_is_limited_and_editorial_not_sku_photo():
    _,bundle=sample_bundle()
    items=bundle["media_manifest"]
    assert [i["role"] for i in items] == ["hero","collection","story"]
    assert all("No text" in item["prompt"] and "not" in item["provenance"] for item in items)
    assert all("шоколад" in item["prompt"].lower() or "chocol" in item["prompt"].lower() for item in items)
    assert all(len(item["prompt"]) <= 1300 for item in items)
    assert len({i["key"] for i in items}) == 3


def test_site_bound_asset_store_idempotency_and_expiry(tmp_path):
    repo=JobRepository(f"sqlite:///{tmp_path/'media.sqlite3'}")
    try:
        store=MediaStore(repo.engine)
        data=[{'key':'hero','role':'hero','alt':'illustrative','provenance':'ai'}]
        first=store.create('site-A','plan-1',data)
        assert first['job_id']==store.create('site-A','plan-1',data)['job_id']
        assert store.get('site-B',first['job_id']) is None
        assert store.count_today('site-A') == 1
        store.save_asset('site-A',first['job_id'],'hero',b'webpbytes')
        assert store.asset('site-A',first['job_id'],'hero')==b'webpbytes'
        assert store.asset('site-B',first['job_id'],'hero') is None
        store.update('site-A',first['job_id'],status='completed')
        assert store.get('site-A',first['job_id'])['status']=='completed'
    finally:
        repo.close()


def test_ai_generated_role_is_not_fabricated_product_photo():
    _,bundle=sample_bundle()
    from app.models import ExperienceSpec
    exp=ExperienceSpec.model_validate(bundle['experience_spec'])
    page=next(p for p in exp.pages if p.page_slug=='home')
    media=[]
    for ix,role in enumerate(('hero','collection','story'), start=101):
        media.append({'id':ix,'url':f'https://mywp.example/wp-content/uploads/{role}.webp',
                      'ai_generated_role':role,'ai_provenance':'ai_generated_concept_not_product_photo'})
    output=compile_elementor_page(page,exp.design_system,media=media,product_names=[])
    nodes=list(walk(output))
    image_ids=[node['settings']['image']['id'] for node in nodes if node.get('widgetType')=='image']
    assert 101 in image_ids and 102 in image_ids and 103 in image_ids
    assert not any('tai-product-card-with-photo' in n.get('settings',{}).get('css_classes','') for n in nodes)
    assert any('tai-editorial-media-story' in n.get('settings',{}).get('css_classes','') for n in nodes)
    assert any('tai-editorial-media-collection' in n.get('settings',{}).get('css_classes','') for n in nodes)
    # Owner's genuine photo takes precedence over AI concept for Hero.
    media.insert(0,{'id':99,'url':'https://mywp.example/owner.jpg','preferred_home_hero':True})
    compiled=compile_elementor_page(page,exp.design_system,media=media)
    assert 99 in [n['settings']['image']['id'] for n in walk(compiled) if n.get('widgetType')=='image']


def test_image_provider_rejects_invalid_dimensions_without_network():
    from app.image_provider import generate_concept
    import pytest
    with pytest.raises(ValueError,match='dimensions'):
        asyncio.run(generate_concept('a','18x19',api_key='dummy',model='fake'))


def test_full_media_job_and_recompile_without_new_text_agent_calls(tmp_path,monkeypatch):
    repo=JobRepository(f"sqlite:///{tmp_path/'jobs.sqlite3'}")
    old_repo, old_store = api.repository, api.media_store
    monkeypatch.setattr(api,'repository',repo)
    monkeypatch.setattr(api,'media_store',MediaStore(repo.engine))
    monkeypatch.setattr(api,'_credentials',lambda site_id, authorization: object())
    monkeypatch.setattr(api.settings,'enable_image_generation',True)
    monkeypatch.setattr(api.settings,'openai_api_key','FAKE-UNIT-TEST-KEY-NOT-REAL')
    site='site-unit-test'
    plan_id=str(uuid.uuid4())
    snapshot,bundle=sample_bundle()
    repo.put({'site_id':site,'job_id':plan_id,'status':'completed','result':bundle})
    calls=[]
    async def fake_image(prompt,size,**kwargs):
        calls.append((size,prompt))
        return b'RIFF'+b'\x00'*4+b'WEBP'+b'X'*400
    monkeypatch.setattr(api,'generate_concept',fake_image)
    try:
        with TestClient(api.app) as client:
            head={'Authorization':'Bearer fake-test-site-token'}
            path=f'/v2/sites/{site}/media-jobs'
            started=client.post(path,json={'plan_job_id':plan_id,'roles':['hero','collection','story']},headers=head)
            assert started.status_code==202, started.text
            job_id=started.json()['job_id']
            same=client.post(path,json={'plan_job_id':plan_id,'roles':['hero','collection','story']},headers=head)
            assert same.json()['job_id']==job_id
            for _ in range(60):
                polled=client.get(f'{path}/{job_id}',headers=head)
                if polled.json()['status']=='completed': break
                time.sleep(0.02)
            assert polled.json()['status']=='completed',polled.text
            assert len(calls)==3  # only one paid batch despite repeated start
            wrong=client.get(f'/v2/sites/other/media-jobs/{job_id}/assets/hero',headers=head)
            assert wrong.status_code==404
            image=client.get(f'{path}/{job_id}/assets/hero',headers=head)
            assert image.status_code==200 and image.headers['content-type']=='image/webp'
            assert image.content.startswith(b'RIFF')
            updated=snapshot.model_dump(mode='json')
            updated['media']=[{'id':i,'url':f'https://mywp.test/uploads/{role}.webp',
              'ai_generated_role':role,'ai_media_job_id':job_id} for i,role in enumerate(['hero','collection','story'],start=11)]
            recompile=client.post(f'/v2/sites/{site}/plans/{plan_id}/recompile-media',
               json={'plan_job_id':plan_id,'media_job_id':job_id,'site_snapshot':updated},headers=head)
            assert recompile.status_code==200,recompile.text
            again=client.post(f'/v2/sites/{site}/plans/{plan_id}/recompile-media',
               json={'plan_job_id':plan_id,'media_job_id':job_id,'site_snapshot':updated},headers=head)
            assert again.json()['already_done'] is True
            persisted=repo.get(plan_id,site)['result']
            assert persisted['media_recompiled_job_id']==job_id
            assert len(calls)==3
            pages=[x['action'] for x in persisted['approved_actions']
              if x['action']['ability']=='thesis-ai-bridge/elementor-ensure-draft-page']
            home=next(x for x in pages if x['parameters']['slug']=='home')
            assert {11,12,13} <= {n['settings']['image']['id'] for n in walk(home['parameters']['elements']) if n.get('widgetType')=='image'}
            denied=client.post(path,json={'plan_job_id':plan_id,'roles':['bogus']},headers=head)
            assert denied.status_code==422
    finally:
        monkeypatch.setattr(api,'repository',old_repo)
        monkeypatch.setattr(api,'media_store',old_store)
        repo.close()


def test_bridge_media_is_explicit_and_does_not_allow_remote_html():
    root=Path(__file__).resolve().parents[1]/'plugin/thesis-ai-bridge'
    source=(root/'includes/class-thesis-ai-cloud.php').read_text()
    admin=(root/'includes/class-thesis-ai-bridge-admin.php').read_text()
    bridge=(root/'includes/class-thesis-ai-bridge.php').read_text()
    assert 'name="brief_media_mode"' in admin
    assert 'value="reuse_only"' in admin and 'value="generate_concepts"' in admin
    assert "'media_mode'" in source and "'media_generation'" in source
    assert 'wp_remote_get(' in source and "'redirection' => 0" in source
    assert 'media_handle_sideload(' in source
    assert 'ai_generated_role' in bridge and 'ai_media_job_id' in bridge
    assert 'wp_attachment_is_image' in bridge


def test_ai_hero_image_is_not_lost_to_typographic_scene():
    from app.models import DesignSystem, PageLayoutSpec, SectionLayoutSpec
    from test_v094_quality_first import sample_page
    page=sample_page(with_products=False)
    media=[{'id':201,'url':'https://wp.example/media/hero.webp','ai_generated_role':'hero'}]
    layout=PageLayoutSpec(page_slug='home',sections=[SectionLayoutSpec(section_index=0,
             hero_scene='typographic',visual_treatment='typography')])
    nodes=compile_elementor_page(page,DesignSystem(),media=media,layout=layout)
    assert any(n.get('widgetType')=='image' for n in walk(nodes))
    assert 'tai-scene-editorial' in nodes[0]['settings']['css_classes']


def test_media_disabled_mode_is_safe_and_free(tmp_path,monkeypatch):
    repo=JobRepository(f"sqlite:///{tmp_path/'off.sqlite3'}")
    monkeypatch.setattr(api,'repository',repo)
    monkeypatch.setattr(api,'media_store',MediaStore(repo.engine))
    monkeypatch.setattr(api,'_credentials',lambda site_id, authorization: object())
    monkeypatch.setattr(api.settings,'enable_image_generation',False)
    with TestClient(api.app) as client:
        resp=client.post('/v2/sites/test/media-jobs',
            json={'plan_job_id':str(uuid.uuid4()),'roles':['hero']},headers={'Authorization':'Bearer fake'})
        assert resp.status_code==409
        assert 'disabled' in resp.text
    repo.close()
