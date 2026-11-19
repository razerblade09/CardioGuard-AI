"""Authentication tests for cloud_api: /analyze (device key) and /dispatch (Firebase ID token)."""
import math

import pytest
from fastapi.testclient import TestClient

import cloud_api


@pytest.fixture
def client():
    # No `with` block: skips the startup event, so the demo patient simulator never starts.
    return TestClient(cloud_api.app)


@pytest.fixture
def ecg_payload():
    return {
        "device_id": "cg_test",
        "patient_id": "patient_test",
        "timestamp": "2026-11-19T00:00:00Z",
        "samples": [2048 + 300 * math.sin(i / 8) for i in range(256)],
    }


@pytest.fixture
def dispatch_payload():
    return {"patient_id": "patient_test", "patient_name": "Test Patient", "lat": 14.5, "lng": 121.0}


class FakeFirebaseAuth:
    """Stands in for firebase_admin.auth. Accepts tokens of the form 'good:<email>'."""
    def verify_id_token(self, token):
        if token.startswith("good:"):
            return {"uid": "u1", "email": token.split(":", 1)[1]}
        raise ValueError("bad token")


@pytest.fixture
def firebase_ready(monkeypatch):
    monkeypatch.setattr(cloud_api, "firebase_db", object())   # truthy: "connected"
    monkeypatch.setattr(cloud_api, "firebase_auth", FakeFirebaseAuth())


# ─── /analyze: device API key ─────────────────────────────────────────────────
def test_analyze_open_when_key_not_configured(client, ecg_payload, monkeypatch):
    monkeypatch.setattr(cloud_api, "DEVICE_API_KEY", "")
    assert client.post("/analyze", json=ecg_payload).status_code == 200


def test_analyze_rejects_missing_key(client, ecg_payload, monkeypatch):
    monkeypatch.setattr(cloud_api, "DEVICE_API_KEY", "s3cret")
    assert client.post("/analyze", json=ecg_payload).status_code == 401


def test_analyze_rejects_wrong_key(client, ecg_payload, monkeypatch):
    monkeypatch.setattr(cloud_api, "DEVICE_API_KEY", "s3cret")
    r = client.post("/analyze", json=ecg_payload, headers={"X-API-Key": "nope"})
    assert r.status_code == 401


def test_analyze_accepts_correct_key(client, ecg_payload, monkeypatch):
    monkeypatch.setattr(cloud_api, "DEVICE_API_KEY", "s3cret")
    r = client.post("/analyze", json=ecg_payload, headers={"X-API-Key": "s3cret"})
    assert r.status_code == 200
    assert r.json()["prediction"] in cloud_api.CLASS_NAMES


# ─── /dispatch: doctor's Firebase ID token ────────────────────────────────────
def test_dispatch_unavailable_without_firebase(client, dispatch_payload, monkeypatch):
    monkeypatch.setattr(cloud_api, "firebase_db", None)
    r = client.post("/dispatch", json=dispatch_payload, headers={"Authorization": "Bearer good:a@b.c"})
    assert r.status_code == 503   # fails closed: cannot verify, so refuse


def test_dispatch_rejects_missing_token(client, dispatch_payload, firebase_ready):
    assert client.post("/dispatch", json=dispatch_payload).status_code == 401


def test_dispatch_rejects_non_bearer_scheme(client, dispatch_payload, firebase_ready):
    r = client.post("/dispatch", json=dispatch_payload, headers={"Authorization": "Basic abc"})
    assert r.status_code == 401


def test_dispatch_rejects_invalid_token(client, dispatch_payload, firebase_ready):
    r = client.post("/dispatch", json=dispatch_payload, headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_dispatch_accepts_valid_token(client, dispatch_payload, firebase_ready, monkeypatch):
    monkeypatch.setattr(cloud_api, "DISPATCH_ALLOWED_EMAILS", set())
    r = client.post("/dispatch", json=dispatch_payload, headers={"Authorization": "Bearer good:dr@clinic.ph"})
    assert r.status_code == 200


def test_dispatch_allowlist_blocks_other_users(client, dispatch_payload, firebase_ready, monkeypatch):
    monkeypatch.setattr(cloud_api, "DISPATCH_ALLOWED_EMAILS", {"dr@clinic.ph"})
    r = client.post("/dispatch", json=dispatch_payload, headers={"Authorization": "Bearer good:stranger@x.com"})
    assert r.status_code == 403


def test_dispatch_allowlist_allows_listed_user_case_insensitive(client, dispatch_payload, firebase_ready, monkeypatch):
    monkeypatch.setattr(cloud_api, "DISPATCH_ALLOWED_EMAILS", {"dr@clinic.ph"})
    r = client.post("/dispatch", json=dispatch_payload, headers={"Authorization": "Bearer good:DR@Clinic.PH"})
    assert r.status_code == 200
