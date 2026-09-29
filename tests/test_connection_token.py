from pathlib import Path

from app.connection_token import ConnectionTokenCodec


def test_stateless_connection_token_roundtrip(tmp_path: Path):
    codec = ConnectionTokenCodec("stable-test-secret", tmp_path / "fallback.key")
    site_id, token = codec.issue(
        site_url="https://example.com",
        username="thesis_ai_builder",
        application_password="app-password-secret",
        bridge_version="0.5.0",
        site_name="Example",
    )
    assert codec.persistent is True
    assert "app-password-secret" not in token

    creds = codec.decode(site_id, token)
    assert creds is not None
    assert creds.site_url == "https://example.com"
    assert creds.username == "thesis_ai_builder"
    assert creds.application_password == "app-password-secret"
    assert codec.decode("different-site", token) is None
    assert codec.decode(site_id, token + "x") is None


def test_same_secret_survives_codec_recreation(tmp_path: Path):
    first = ConnectionTokenCodec("stable-test-secret", tmp_path / "one.key")
    site_id, token = first.issue(
        site_url="https://example.com",
        username="u",
        application_password="p",
        bridge_version="0.5.0",
        site_name="Example",
    )
    second = ConnectionTokenCodec("stable-test-secret", tmp_path / "two.key")
    assert second.decode(site_id, token) is not None
