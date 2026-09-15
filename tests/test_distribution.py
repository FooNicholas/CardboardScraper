from pathlib import Path

import httpx
import pytest

from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.distribution import (
    CatalogueSnapshotError,
    CatalogueUpdateClient,
    create_catalogue_snapshot,
    read_local_snapshot,
    replace_catalogue_atomically,
    seed_bundled_catalogue,
)
from scraperbot.models import CardPrint
from scraperbot.services.comparison import ComparisonService
from scraperbot.web import LocalPriceCheckWeb


def _catalogue(path: Path, english_name: str) -> None:
    with CatalogueRepository(path) as catalogue:
        catalogue.upsert(
            CardPrint(
                "DZ-BT16",
                "001",
                "RRR",
                english_name,
                japanese_name="テストカード",
                source="test",
            )
        )


def test_snapshot_seeds_a_writable_user_catalogue_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "curator.sqlite3"
    _catalogue(source, "Bundled Card")
    bundle = tmp_path / "bundle"
    snapshot = create_catalogue_snapshot(source, bundle, version="2026.09.15")
    target = tmp_path / "user-data" / "catalogue.sqlite3"
    monkeypatch.setenv("SCRAPERBOT_BUNDLED_CATALOGUE", str(bundle))

    assert seed_bundled_catalogue(target) is True
    assert read_local_snapshot(target) == snapshot
    with CatalogueRepository(target) as catalogue:
        assert catalogue.search("bundled", japanese_only=True)[0].english_name == "Bundled Card"
    assert seed_bundled_catalogue(target) is False


def test_update_client_downloads_a_hash_checked_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "curator.sqlite3"
    _catalogue(source, "New Card")
    assets = tmp_path / "assets"
    snapshot = create_catalogue_snapshot(source, assets, version="2026.09.16")
    manifest_url = "https://example.test/releases/latest/download/catalogue-manifest.json"
    database_url = "https://example.test/releases/latest/download/catalogue.sqlite3"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == manifest_url:
            return httpx.Response(200, json=snapshot.to_dict(), request=request)
        if str(request.url) == database_url:
            return httpx.Response(
                200,
                content=(assets / "catalogue.sqlite3").read_bytes(),
                headers={"Content-Length": str(snapshot.size_bytes)},
                request=request,
            )
        return httpx.Response(404, request=request)

    client = CatalogueUpdateClient(manifest_url, client=httpx.Client(transport=httpx.MockTransport(handler)))
    target = tmp_path / "target"

    assert client.status(target / "catalogue.sqlite3").status == "update_available"
    staged = client.stage_snapshot(client.fetch_snapshot(), target)
    assert staged.is_file()
    backup = replace_catalogue_atomically(staged, target / "catalogue.sqlite3", snapshot)
    assert backup is None
    assert read_local_snapshot(target / "catalogue.sqlite3") == snapshot


def test_update_client_rejects_a_snapshot_with_the_wrong_checksum(tmp_path: Path) -> None:
    source = tmp_path / "curator.sqlite3"
    _catalogue(source, "New Card")
    assets = tmp_path / "assets"
    snapshot = create_catalogue_snapshot(source, assets, version="2026.09.16")
    manifest_url = "https://example.test/releases/latest/download/catalogue-manifest.json"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("catalogue-manifest.json"):
            manifest = snapshot.to_dict()
            manifest["sha256"] = "0" * 64
            return httpx.Response(200, json=manifest, request=request)
        return httpx.Response(200, content=(assets / "catalogue.sqlite3").read_bytes(), request=request)

    client = CatalogueUpdateClient(manifest_url, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(CatalogueSnapshotError, match="checksum"):
        client.stage_snapshot(client.fetch_snapshot(), tmp_path / "target")


def test_web_app_reopens_the_catalogue_after_an_explicit_update(tmp_path: Path) -> None:
    current = tmp_path / "user" / "catalogue.sqlite3"
    _catalogue(current, "Old Card")
    source = tmp_path / "curator.sqlite3"
    _catalogue(source, "Updated Card")
    assets = tmp_path / "assets"
    snapshot = create_catalogue_snapshot(source, assets, version="2026.09.16")
    manifest_url = "https://example.test/releases/latest/download/catalogue-manifest.json"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("catalogue-manifest.json"):
            return httpx.Response(200, json=snapshot.to_dict(), request=request)
        return httpx.Response(
            200,
            content=(assets / "catalogue.sqlite3").read_bytes(),
            headers={"Content-Length": str(snapshot.size_bytes)},
            request=request,
        )

    client = CatalogueUpdateClient(manifest_url, client=httpx.Client(transport=httpx.MockTransport(handler)))
    catalogue = CatalogueRepository(current)
    app = LocalPriceCheckWeb(catalogue, ComparisonService([]), update_client=client)
    try:
        result = app.apply_catalogue_update()
        assert result["status"] == "updated"
        assert app.search("updated")["cards"]
        assert app.search("old")["cards"] == []
    finally:
        app.catalogue.close()
