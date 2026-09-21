# ruff: noqa: I001, S101

from pathlib import Path


ROOT = Path(__file__).parents[2]
TRAEFIK = ROOT / "infra/dokploy/traefik/traefik.yml"
DYNAMIC = ROOT / "infra/dokploy/traefik/dynamic.yml"
SYNC = ROOT / "infra/dokploy/scripts/sync-traefik-config.sh"


def test_api_route_and_runtime_paths_share_the_same_source_of_truth():
    static = TRAEFIK.read_text()
    dynamic = DYNAMIC.read_text()
    sync = SYNC.read_text()

    assert "directory: /etc/dokploy/traefik/dynamic" in static
    assert "Host(`api.skatelab.ru`) && PathPrefix(`/v1/`)" in dynamic
    assert 'url: "http://backend-dk:8000"' in dynamic
    assert 'REMOTE_STATIC="/etc/dokploy/traefik/traefik.yml"' in sync
    assert 'REMOTE_DYNAMIC="/etc/dokploy/traefik/dynamic/skatelab.yml"' in sync
    assert "https://api.skatelab.ru/v1/health" in sync
