"""SPA serving tests (M004 PR3, app/spa.py + main.py wiring).

Supervisor-gated mount design, verified here:

* API route precedence is structural — /api/*, /health, /metrics, /monitor
  always win over the mount.
* No blanket fallback — missing files (paths with extensions) stay hard
  404s; unknown /api/* paths keep the backend's JSON 404.
* The frontend is optional — with no built dist the app runs exactly as
  before (the rest of the suite is the proof; the tests below pin the
  behaviour explicitly).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.spa import DEFAULT_DIST_DIR, SpaStaticFiles, resolve_dist_dir
from app.storage.memory import (
    InMemoryEventStorage,
    InMemoryHostInventoryStorage,
    InMemoryMissionStorage,
    InMemoryRegistryStorage,
)
from tests.conftest import TEST_KEY_BINDINGS, auth_headers

INDEX_HTML = "<!doctype html><html><body><div id=root>observatory-spa</div></body></html>"


def _settings(dist_dir: str) -> Settings:
    return Settings(
        _env_file=None,
        api_keys=",".join(f"{cid}:{key}" for key, cid in TEST_KEY_BINDINGS.items()),
        app_version="0.0.0-test",
        max_request_bytes=4096,
        background_tasks_enabled=False,
        frontend_dist_dir=dist_dir,
    )


def _client(dist_dir: str) -> TestClient:
    app = create_app(
        settings=_settings(dist_dir),
        storage=InMemoryEventStorage(),
        registry_storage=InMemoryRegistryStorage(),
        mission_storage=InMemoryMissionStorage(),
        inventory_storage=InMemoryHostInventoryStorage(),
    )
    return TestClient(app)


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """A minimal Vite-style production build."""
    (tmp_path / "index.html").write_text(INDEX_HTML)
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('observatory')")
    (tmp_path / "favicon.svg").write_text("<svg></svg>")
    return tmp_path


def test_index_and_assets_served(dist: Path) -> None:
    with _client(str(dist)) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "observatory-spa" in root.text
        asset = client.get("/assets/app.js")
        assert asset.status_code == 200
        assert "observatory" in asset.text


def test_navigation_paths_fall_back_to_index(dist: Path) -> None:
    """Extension-less client routes (deep links) get index.html — the client
    router owns the not-found experience."""
    with _client(str(dist)) as client:
        for path in ("/fleet", "/fleet/RPSG01", "/settings", "/events"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert "observatory-spa" in response.text, path


def test_missing_asset_is_hard_404(dist: Path) -> None:
    """A broken asset reference must fail loudly, never deliver index.html."""
    with _client(str(dist)) as client:
        for path in ("/assets/gone.js", "/missing.css", "/fleet/logo.png"):
            response = client.get(path)
            assert response.status_code == 404, path
            assert "observatory-spa" not in response.text, path


def test_unknown_api_path_stays_json_404(dist: Path) -> None:
    """A typo'd endpoint returns the backend's JSON 404, never HTML."""
    with _client(str(dist)) as client:
        response = client.get("/api/v1/does-not-exist", headers=auth_headers())
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}


def test_api_routes_keep_precedence(dist: Path) -> None:
    """Registered routes always win over the mount."""
    with _client(str(dist)) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] in ("ok", "degraded")

        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "observatory" in metrics.text

        monitor = client.get("/monitor")
        assert monitor.status_code == 200
        assert "observatory-spa" not in monitor.text  # server-rendered page, not the SPA

        fleet = client.get("/api/v1/fleet", headers=auth_headers())
        assert fleet.status_code == 200
        assert isinstance(fleet.json(), list)


def test_no_dist_means_no_mount(tmp_path: Path) -> None:
    """Deployments without a built frontend run exactly as before."""
    with _client(str(tmp_path / "nonexistent")) as client:
        assert client.get("/").status_code == 404
        assert client.get("/fleet").status_code == 404
        assert client.get("/health").status_code == 200


def test_resolve_dist_dir_defaults_to_repo_frontend() -> None:
    assert resolve_dist_dir("") == DEFAULT_DIST_DIR
    assert DEFAULT_DIST_DIR.parts[-2:] == ("frontend", "dist")
    assert resolve_dist_dir("/opt/console/dist") == Path("/opt/console/dist")


def test_navigation_path_predicate() -> None:
    """Unit contract for the fallback guard: extension-less, non-API only."""
    is_nav = SpaStaticFiles._is_navigation_path
    assert is_nav("fleet/RPSG01")
    assert is_nav("settings")
    assert not is_nav("api/v1/anything")
    assert not is_nav("assets/app.js")
    assert not is_nav("fleet/logo.png")
