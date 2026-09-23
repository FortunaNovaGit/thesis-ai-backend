from pathlib import Path

from app.site_store import SiteStore


def test_site_store_encrypts_password_and_authenticates(tmp_path: Path):
    store = SiteStore(tmp_path / "sites.json", tmp_path / "backend.key")
    site_id, token = store.register(
        site_url="https://example.com",
        username="thesis_ai_builder",
        application_password="plain-secret-password",
        bridge_version="0.3.0",
        site_name="Example",
    )

    raw = (tmp_path / "sites.json").read_text(encoding="utf-8")
    assert "plain-secret-password" not in raw
    assert token not in raw
    assert store.authenticate(site_id, token)
    assert not store.authenticate(site_id, token + "x")

    creds = store.credentials(site_id)
    assert creds is not None
    assert creds.application_password == "plain-secret-password"
    assert creds.site_url == "https://example.com"

    assert store.delete(site_id)
    assert store.credentials(site_id) is None
