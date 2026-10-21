"""Protect pre-existing resources before the smoke runner acquires ownership."""

from types import SimpleNamespace

import pytest

from scripts.run_container_smoke import Smoke, isolated_environment


@pytest.mark.parametrize("kind", ["ps", "volume"])
def test_existing_resources_are_never_started_or_cleaned(monkeypatch, kind):
    calls = []

    def run(self, args, **kwargs):
        calls.append(args)
        return SimpleNamespace(
            stdout="existing-resource" if args[1] == kind else "", returncode=0
        )

    monkeypatch.setattr(Smoke, "run", run)
    smoke = Smoke("voc-smoke-owned-by-someone-else", 18000, 13000)
    with pytest.raises(RuntimeError, match="already has resources"):
        smoke.execute(build=True)
    assert calls
    assert all(args[1] in ("ps", "volume") for args in calls)


@pytest.mark.parametrize(
    "project", ["voc-local", "voc_postgres", "voc-smoke-../old", "voc-smoke-"]
)
def test_unsafe_project_names_are_rejected(project):
    with pytest.raises(ValueError, match="Project must"):
        Smoke(project, 18000, 13000)


def test_shell_compose_settings_do_not_redirect_test_resources(monkeypatch):
    monkeypatch.setenv("COMPOSE_FILE", "old-compose.yml")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "old-project")
    monkeypatch.setenv("VOC_EMBEDDING_BASE_URL", "https://real-provider.invalid")
    monkeypatch.setenv("VOC_EMBEDDING_API_KEY", "must-not-reach-compose")
    monkeypatch.setenv("DOCKER_HOST", "npipe:////./pipe/docker_engine")
    env = isolated_environment(18000, 13000)
    assert not any(key.upper().startswith("COMPOSE_") for key in env)
    assert "VOC_EMBEDDING_BASE_URL" not in env
    assert "VOC_EMBEDDING_API_KEY" not in env
    assert env["VOC_API_PORT"] == "18000"
    assert env["DOCKER_HOST"] == "npipe:////./pipe/docker_engine"
