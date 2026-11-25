"""v0.13 auto imagery: one generated concept per image-friendly section.

Offline only: the image provider is faked, no paid API calls.
"""
import asyncio
import re
import time
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app import api
from app.component_library import compile_elementor_page, choose_secondary_page_media
from app.media_pipeline import page_media_slots, build_media_manifest, HARD_MAX_IMAGES
from app.media_store import MediaStore
from app.models import (DesignSystem, ExperienceSpec, PageExperienceSpec, ProjectBrief, SectionContentSpec,
                        SeoSpec)
from app.repository import JobRepository
from test_v011_media_pipeline import sample_bundle
from test_v094_quality_first import walk

PLUGIN = Path(__file__).resolve().parents[1] / "plugin/thesis-ai-bridge"


def page(slug, types):
    specs = []
    for i, t in enumerate(types):
        items = [] if t in {"hero", "statement", "cta"} else [f"Пункт {i}{j} — пояснення {j}" for j in range(3)]
        specs.append(SectionContentSpec(section_type=t, heading=f"Секція {slug} {i} {t}",
                                        body="Короткий опис секції для відвідувача.", items=items,
                                        cta_label="Дізнатися більше" if t in {"hero", "cta"} else "",
                                        cta_url="/shop/" if t in {"hero", "cta"} else "",
                                        style_variant="dark" if t == "cta" else "default"))
    return PageExperienceSpec(page_name=slug.title(), page_slug=slug, page_goal="Мета сторінки",
                              sections=types, section_specs=specs,
                              seo=SeoSpec(slug=f"/{slug}/", title=slug, meta_description="Опис", h1=specs[0].heading))


HOME = ["hero", "benefits", "process", "products", "statement", "faq", "team", "stats", "cta"]


def media_for(slots, start=500):
    return [{"id": start + i, "url": f"https://wp.example/uploads/{s['key']}.webp",
             "ai_generated_role": s["key"], "ai_provenance": "ai_generated_concept_not_product_photo"}
            for i, s in enumerate(slots)]


def test_slots_are_deterministic_unique_and_skip_people_and_numbers():
    slots = page_media_slots("home", HOME)
    keys = [s["key"] for s in slots]
    assert keys == ["hero", "hero-detail", "story", "process", "collection", "statement", "faq", "cta"]
    assert len(set(keys)) == len(keys)
    assert not {"team", "stats"} & {s["kind"] for s in slots}
    assert page_media_slots("home", HOME) == slots
    other = [s["key"] for s in page_media_slots("contacts", ["hero", "contact", "booking", "faq"])]
    assert other == ["contacts-hero", "contacts-contact", "contacts-booking", "contacts-faq"]
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9-]{1,31}", k) for k in keys + other)


def test_manifest_cap_and_priority():
    exp = ExperienceSpec.model_validate(sample_bundle()[1]["experience_spec"])
    brief = ProjectBrief.model_validate(sample_bundle()[1]["project_brief"])
    three = build_media_manifest(brief, exp, "шоколад", max_images=3)
    assert [i["key"] for i in three] == ["hero", "story", "collection"]
    full = build_media_manifest(brief, exp, "шоколад", max_images=99)
    assert len(full) <= HARD_MAX_IMAGES
    keys = [i["key"] for i in full]
    # Other pages' openings come before the rest of the home sections.
    assert keys.index("about-hero") < keys.index("cta")
    assert all(i["size"] in {"1024x1024", "1536x1024", "1024x1536"} for i in full)


def test_every_slot_image_lands_once_in_its_own_section():
    home = page("home", HOME)
    slots = page_media_slots("home", HOME)
    media = media_for(slots)
    nodes = compile_elementor_page(home, DesignSystem(), media=media)
    ids = [n["settings"]["image"]["id"] for n in walk(nodes) if n.get("widgetType") == "image"]
    expected = {m["id"] for m in media if m["ai_generated_role"] != "hero-detail"}  # no layout → single hero
    assert expected <= set(ids)
    assert len(ids) == len(set(ids)), "an image must never be used twice"
    by_type = {n["settings"]["css_classes"].split()[1]: n for n in nodes}
    assert "tai-split-head" in str(by_type["thesis-ai-benefits"])
    assert "tai-has-bg-media" in by_type["thesis-ai-cta"]["settings"]["css_classes"]
    assert "tai-has-bg-media" in by_type["thesis-ai-statement"]["settings"]["css_classes"]
    faq_intro = next(n for n in walk(nodes) if "tai-faq-intro" in n.get("settings", {}).get("css_classes", ""))
    assert any(n.get("widgetType") == "image" for n in walk([faq_intro]))
    # Team and stats sections never receive generated imagery.
    for key in ("thesis-ai-team", "thesis-ai-stats"):
        assert not any(n.get("widgetType") == "image" for n in walk([by_type[key]]))
    # Generated concepts never become product photos.
    assert not any("tai-product-card-with-photo" in n.get("settings", {}).get("css_classes", "") for n in walk(nodes))


def test_split_images_alternate_sides():
    home = page("home", ["hero", "benefits", "services", "process"])
    nodes = compile_elementor_page(home, DesignSystem(), media=media_for(page_media_slots("home", home.sections)))
    splits = [n for n in walk(nodes) if "tai-split-head" in n.get("settings", {}).get("css_classes", "")]
    assert len(splits) == 3
    assert ["tai-split-flip" in s["settings"]["css_classes"] for s in splits] == [False, True, False]


def test_pages_use_only_their_own_images():
    contacts = page("contacts", ["hero", "contact", "faq"])
    media = media_for(page_media_slots("home", HOME)) + media_for(page_media_slots("contacts", contacts.sections), 900)
    nodes = compile_elementor_page(contacts, DesignSystem(), media=media)
    ids = {n["settings"]["image"]["id"] for n in walk(nodes) if n.get("widgetType") == "image"}
    assert ids == {900, 901, 902}


def test_owner_photo_still_wins_and_detail_is_secondary():
    home = page("home", HOME)
    media = media_for(page_media_slots("home", HOME))
    media.insert(0, {"id": 77, "url": "https://wp.example/owner.jpg", "preferred_home_hero": True})
    nodes = compile_elementor_page(home, DesignSystem(), media=media)
    hero_ids = [n["settings"]["image"]["id"] for n in walk([nodes[0]]) if n.get("widgetType") == "image"]
    assert hero_ids[0] == 77 and 500 not in hero_ids
    secondary = choose_secondary_page_media(home, media, media[0])
    assert secondary is not None and secondary["ai_generated_role"] == "hero-detail"


def test_no_media_keeps_truthful_typographic_layout():
    nodes = compile_elementor_page(page("home", HOME), DesignSystem(), media=[])
    assert not any(n.get("widgetType") == "image" for n in walk(nodes))
    assert not any("tai-has-media" in n.get("settings", {}).get("css_classes", "") for n in nodes)


def _client(tmp_path, monkeypatch, fake):
    repo = JobRepository(f"sqlite:///{tmp_path/'jobs.sqlite3'}")
    monkeypatch.setattr(api, "repository", repo)
    monkeypatch.setattr(api, "media_store", MediaStore(repo.engine))
    monkeypatch.setattr(api, "_credentials", lambda site_id, authorization: object())
    monkeypatch.setattr(api.settings, "enable_image_generation", True)
    monkeypatch.setattr(api.settings, "openai_api_key", "FAKE-UNIT-TEST-KEY-NOT-REAL")
    monkeypatch.setattr(api, "generate_concept", fake)
    plan_id = str(uuid.uuid4())
    _, bundle = sample_bundle()
    repo.put({"site_id": "site-x", "job_id": plan_id, "status": "completed", "result": bundle})
    return repo, plan_id, bundle


def _poll(client, path, head):
    for _ in range(100):
        body = client.get(path, headers=head).json()
        if body["status"] in {"completed", "failed"}:
            return body
        time.sleep(0.02)
    return body


def test_all_manifest_roles_generate_and_one_failure_is_partial(tmp_path, monkeypatch):
    calls = []

    async def fake(prompt, size, **kwargs):
        calls.append(size)
        if "Section theme" in prompt and len(calls) == 2:
            raise RuntimeError("provider refused one image")
        return b"RIFF" + b"\x00" * 4 + b"WEBP" + b"X" * 400

    repo, plan_id, bundle = _client(tmp_path, monkeypatch, fake)
    roles = [i["role"] for i in bundle["media_manifest"]]
    try:
        with TestClient(api.app) as client:
            head = {"Authorization": "Bearer fake"}
            path = "/v2/sites/site-x/media-jobs"
            started = client.post(path, json={"plan_job_id": plan_id, "roles": roles}, headers=head)
            assert started.status_code == 202, started.text
            job = _poll(client, f"{path}/{started.json()['job_id']}", head)
            assert job["status"] == "completed"
            assert len(calls) == len(roles)
            assert len(job["assets"]) == len(roles) - 1 and "skipped" in job["error"]
            off_plan = client.post(path, json={"plan_job_id": plan_id, "roles": ["contacts-faq-not-in-plan"]}, headers=head)
            assert off_plan.status_code == 422
    finally:
        repo.close()


def test_roles_outside_the_plan_are_rejected(tmp_path, monkeypatch):
    async def fake(prompt, size, **kwargs):
        return b"RIFF" + b"\x00" * 4 + b"WEBP" + b"X" * 400
    repo, plan_id, _ = _client(tmp_path, monkeypatch, fake)
    try:
        with TestClient(api.app) as client:
            r = client.post("/v2/sites/site-x/media-jobs",
                            json={"plan_job_id": plan_id, "roles": ["hero", "not-in-plan"]},
                            headers={"Authorization": "Bearer fake"})
            assert r.status_code == 422
            r = client.post("/v2/sites/site-x/media-jobs",
                            json={"plan_job_id": plan_id, "roles": ["../../etc"]},
                            headers={"Authorization": "Bearer fake"})
            assert r.status_code == 422
    finally:
        repo.close()


def test_all_images_failing_marks_job_failed(tmp_path, monkeypatch):
    async def fake(prompt, size, **kwargs):
        raise RuntimeError("down")
    repo, plan_id, bundle = _client(tmp_path, monkeypatch, fake)
    try:
        with TestClient(api.app) as client:
            head = {"Authorization": "Bearer fake"}
            started = client.post("/v2/sites/site-x/media-jobs",
                                  json={"plan_job_id": plan_id, "roles": ["hero", "story"]}, headers=head)
            job = _poll(client, f"/v2/sites/site-x/media-jobs/{started.json()['job_id']}", head)
            assert job["status"] == "failed"
    finally:
        repo.close()


def test_bridge_auto_mode_defaults_and_never_fails_build_on_media():
    admin = (PLUGIN / "includes/class-thesis-ai-bridge-admin.php").read_text()
    cloud = (PLUGIN / "includes/class-thesis-ai-cloud.php").read_text()
    bridge = (PLUGIN / "includes/class-thesis-ai-bridge.php").read_text()
    assert "$brief['media_mode'] = $mode === 'reuse_only' ? 'reuse_only' : 'auto';" in admin
    assert "Thesis_AI_Cloud::brief_media_mode" in admin
    assert "public static function brief_media_mode" in cloud
    assert "if (empty($brief['media_mode_v'])) { return 'auto'; }" in cloud
    poll_media = cloud[cloud.index("private static function poll_media"):cloud.index("private static function sideload_concept_image")]
    assert "finalize_failed_build" not in poll_media
    assert poll_media.count("skip_media(") >= 2
    assert "['hero', 'collection', 'story']" not in cloud
    assert "/^[a-z0-9][a-z0-9-]{1,31}$/" in cloud
    assert "'posts_per_page' => 40" in bridge
    css = (PLUGIN / "assets/rich-sections.css").read_text()
    for cls in (".tai-split-head", ".tai-bg-media", ".tai-has-bg-media", ".tai-section-media-products"):
        assert cls in css
