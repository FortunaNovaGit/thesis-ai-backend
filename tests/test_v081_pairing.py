from fastapi.testclient import TestClient
from app import api


def test_protected_pairing_denies_missing_secret(monkeypatch):
    monkeypatch.setattr(api.settings, 'backend_pairing_secret', 'long-test-pairing-secret')
    monkeypatch.setattr(api.settings, 'allow_private_wordpress', True)
    with TestClient(api.app) as client:
        response = client.post('/v2/sites/connect', json={'site_url': 'https://demo.test'})
        assert response.status_code == 403
        allowed = client.post('/v2/sites/connect', json={'site_url': 'https://demo.test'},
            headers={'X-Thesis-Pairing-Secret': 'long-test-pairing-secret'})
        assert allowed.status_code == 200
