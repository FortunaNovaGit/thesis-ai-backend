import time
from fastapi.testclient import TestClient
from app import api
from app.repository import JobRepository


def test_connection_plan_and_revocation(tmp_path, monkeypatch):
    old_repo = api.repository
    new_repo = JobRepository(f"sqlite:///{tmp_path / 'jobs.sqlite3'}")
    monkeypatch.setattr(api, 'repository', new_repo)
    monkeypatch.setattr(api.settings, 'allow_private_wordpress', True)
    monkeypatch.setattr(api.settings, 'agent_mode', 'mock')
    try:
        with TestClient(api.app) as client:
            health = client.get('/health')
            assert health.status_code == 200
            assert health.json()['version'] == '0.8.4'
            conn = client.post('/v2/sites/connect', json={"site_url": "https://demo.test", "bridge_version": "0.8.1"})
            assert conn.status_code == 200
            site_id = conn.json()['site_id']
            headers = {"Authorization": f"Bearer {conn.json()['site_token']}"}
            payload = {"request": "Створи сучасний сайт стоматологічної клініки", "renderer": "elementor", "site_snapshot": {}}
            started = client.post(f'/v2/sites/{site_id}/plans', json=payload, headers=headers)
            assert started.status_code == 202, started.text
            job_id = started.json()['job_id']
            for _ in range(80):
                item = client.get(f'/v2/sites/{site_id}/plans/{job_id}', headers=headers)
                assert item.status_code == 200
                if item.json()['status'] in ['completed', 'failed']:
                    break
                time.sleep(0.05)
            assert item.json()['status'] == 'completed', item.text
            assert new_repo.get(job_id, site_id)['status'] == 'completed'
            assert '_payload' not in item.json()
            disconnected = client.post(f'/v2/sites/{site_id}/disconnect', headers=headers)
            assert disconnected.status_code == 200
            denied = client.get(f'/v2/sites/{site_id}/check', headers=headers)
            assert denied.status_code == 401
    finally:
        monkeypatch.setattr(api, 'repository', old_repo)
        new_repo.close()
