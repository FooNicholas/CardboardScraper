"""Desktop-release catalogue snapshots and explicit update support.

The normal source checkout keeps its database in ``data/``.  A packaged app
instead seeds a writable per-user copy from the catalogue snapshot shipped
inside that release.  New snapshots are curator-built and user-approved: the
app never asks every download to scrape the catalogue sources for itself.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
from tempfile import NamedTemporaryFile
from typing import Iterator
from urllib.parse import urljoin, urlparse

import httpx


APPLICATION_NAME = "JP Price Checker"
SNAPSHOT_FILE_NAME = "catalogue.sqlite3"
SNAPSHOT_MANIFEST_FILE_NAME = "catalogue-manifest.json"
LOCAL_VERSION_FILE_NAME = "catalogue-version.json"
SNAPSHOT_FORMAT_VERSION = 1
MAX_SNAPSHOT_BYTES = 300 * 1024 * 1024
# Release assets must be public for friends to obtain an update without being
# granted repository access. Packaged builds can override this with the
# CATALOGUE_UPDATE_MANIFEST_URL environment variable if the release channel
# moves later.
DEFAULT_UPDATE_MANIFEST_URL = (
    "https://github.com/FooNicholas/ScraperBot/releases/latest/download/"
    f"{SNAPSHOT_MANIFEST_FILE_NAME}"
)


class CatalogueSnapshotError(RuntimeError):
    """A downloaded or packaged catalogue snapshot cannot be trusted."""


@dataclass(frozen=True, slots=True)
class CatalogueSnapshot:
    """Verified metadata for one immutable SQLite catalogue snapshot."""

    catalogue_version: str
    generated_at: str
    database_file: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": SNAPSHOT_FORMAT_VERSION,
            **asdict(self),
        }

    @classmethod
    def from_dict(cls, value: object) -> "CatalogueSnapshot":
        if not isinstance(value, dict):
            raise CatalogueSnapshotError("Catalogue update metadata is not an object.")
        if value.get("format_version") != SNAPSHOT_FORMAT_VERSION:
            raise CatalogueSnapshotError("This catalogue update format is not supported by this app version.")
        catalogue_version = value.get("catalogue_version")
        generated_at = value.get("generated_at")
        database_file = value.get("database_file")
        checksum = value.get("sha256")
        size_bytes = value.get("size_bytes")
        if not isinstance(catalogue_version, str) or not catalogue_version.strip():
            raise CatalogueSnapshotError("Catalogue update metadata has no version.")
        if not isinstance(generated_at, str) or not generated_at.strip():
            raise CatalogueSnapshotError("Catalogue update metadata has no generation time.")
        if (
            not isinstance(database_file, str)
            or Path(database_file).name != database_file
            or database_file != SNAPSHOT_FILE_NAME
        ):
            raise CatalogueSnapshotError("Catalogue update metadata names an invalid database file.")
        if not isinstance(checksum, str) or not re.fullmatch(r"[a-f0-9]{64}", checksum):
            raise CatalogueSnapshotError("Catalogue update metadata has an invalid checksum.")
        if not isinstance(size_bytes, int) or not 1 <= size_bytes <= MAX_SNAPSHOT_BYTES:
            raise CatalogueSnapshotError("Catalogue update metadata has an invalid database size.")
        return cls(catalogue_version.strip(), generated_at.strip(), database_file, checksum, size_bytes)


@dataclass(frozen=True, slots=True)
class CatalogueUpdateStatus:
    """What an explicit user update check found."""

    enabled: bool
    status: str
    current_version: str | None = None
    available_version: str | None = None
    generated_at: str | None = None

    def to_dict(self) -> dict[str, object | None]:
        return asdict(self)


def is_packaged_application() -> bool:
    """Whether Python is executing from a frozen desktop release."""
    return bool(getattr(sys, "frozen", False))


def application_data_directory() -> Path:
    """Return the writable data directory without creating it.

    A source checkout deliberately keeps the historic relative ``data``
    location. Packaged apps must not write beside the installed executable.
    """
    configured = os.getenv("SCRAPERBOT_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    if not is_packaged_application():
        return Path("data")
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APPLICATION_NAME
    if sys.platform.startswith("win"):
        return Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / APPLICATION_NAME
    return Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "jp-price-checker"


def default_catalogue_database() -> Path:
    return application_data_directory() / SNAPSHOT_FILE_NAME


def local_version_path(database: Path) -> Path:
    return database.parent / LOCAL_VERSION_FILE_NAME


def bundled_catalogue_directory() -> Path | None:
    """Locate the catalogue directory that PyInstaller placed in the app."""
    configured = os.getenv("SCRAPERBOT_BUNDLED_CATALOGUE")
    if configured:
        return Path(configured).expanduser()
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "catalogue"
    return None


def read_snapshot_manifest(path: Path) -> CatalogueSnapshot:
    try:
        return CatalogueSnapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except OSError as error:
        raise CatalogueSnapshotError(f"Could not read catalogue metadata: {error}") from error
    except json.JSONDecodeError as error:
        raise CatalogueSnapshotError("Catalogue update metadata is not valid JSON.") from error


def write_snapshot_manifest(path: Path, snapshot: CatalogueSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_local_snapshot(database: Path) -> CatalogueSnapshot | None:
    path = local_version_path(database)
    return read_snapshot_manifest(path) if path.is_file() else None


def validate_catalogue_database(path: Path) -> None:
    """Reject a corrupt or non-catalogue SQLite file before it can replace data."""
    if not path.is_file() or path.stat().st_size <= 0:
        raise CatalogueSnapshotError("Catalogue database file is missing or empty.")
    try:
        connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        try:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
            if not quick_check or quick_check[0] != "ok":
                raise CatalogueSnapshotError("Catalogue database integrity check failed.")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise CatalogueSnapshotError("Catalogue download is not a readable SQLite database.") from error
    required_tables = {"japanese_prints", "card_identities", "japanese_print_identity_links"}
    if not required_tables.issubset(tables):
        raise CatalogueSnapshotError("Catalogue download does not contain the JP Price Checker schema.")


def hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_catalogue_snapshot(source: Path, output_directory: Path, *, version: str) -> CatalogueSnapshot:
    """Copy one validated curator database and write its release manifest."""
    source = source.resolve()
    validate_catalogue_database(source)
    if not version.strip():
        raise CatalogueSnapshotError("Catalogue snapshot version cannot be empty.")
    output_directory.mkdir(parents=True, exist_ok=True)
    destination = output_directory / SNAPSHOT_FILE_NAME
    shutil.copy2(source, destination)
    snapshot = CatalogueSnapshot(
        catalogue_version=version.strip(),
        generated_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
        database_file=SNAPSHOT_FILE_NAME,
        sha256=hash_file(destination),
        size_bytes=destination.stat().st_size,
    )
    write_snapshot_manifest(output_directory / SNAPSHOT_MANIFEST_FILE_NAME, snapshot)
    return snapshot


def _copy_atomically(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(prefix=f".{destination.name}.", suffix=".part", dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def seed_bundled_catalogue(database: Path) -> bool:
    """Install the release snapshot once, without overwriting user data."""
    if database.exists():
        return False
    directory = bundled_catalogue_directory()
    if directory is None:
        return False
    source_database = directory / SNAPSHOT_FILE_NAME
    source_manifest = directory / SNAPSHOT_MANIFEST_FILE_NAME
    if not source_database.is_file() or not source_manifest.is_file():
        return False
    snapshot = read_snapshot_manifest(source_manifest)
    validate_catalogue_database(source_database)
    if source_database.stat().st_size != snapshot.size_bytes or hash_file(source_database) != snapshot.sha256:
        raise CatalogueSnapshotError("Bundled catalogue does not match its release metadata.")
    _copy_atomically(source_database, database)
    write_snapshot_manifest(local_version_path(database), snapshot)
    return True


@contextmanager
def _client_context(client: httpx.Client | None) -> Iterator[httpx.Client]:
    if client is not None:
        yield client
        return
    owned_client = httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30.0, connect=10.0))
    try:
        yield owned_client
    finally:
        owned_client.close()


class CatalogueUpdateClient:
    """Download only a checksum-verified release snapshot after user approval."""

    def __init__(self, manifest_url: str | None, *, client: httpx.Client | None = None) -> None:
        self.manifest_url = manifest_url
        self.client = client

    @property
    def enabled(self) -> bool:
        return bool(self.manifest_url)

    def _manifest_url(self) -> str:
        if not self.manifest_url:
            raise CatalogueSnapshotError("Catalogue updates are not configured for this app build.")
        parsed = urlparse(self.manifest_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise CatalogueSnapshotError("Catalogue updates must use an HTTPS release URL.")
        return self.manifest_url

    def fetch_snapshot(self) -> CatalogueSnapshot:
        manifest_url = self._manifest_url()
        try:
            with _client_context(self.client) as client:
                response = client.get(manifest_url)
                response.raise_for_status()
                response_url = urlparse(str(response.url))
                if response_url.scheme != "https" or not response_url.netloc:
                    raise CatalogueSnapshotError("Catalogue update was redirected away from HTTPS.")
        except httpx.HTTPError as error:
            raise CatalogueSnapshotError("Could not check the published catalogue update.") from error
        try:
            return CatalogueSnapshot.from_dict(response.json())
        except json.JSONDecodeError as error:
            raise CatalogueSnapshotError("Catalogue update metadata is not valid JSON.") from error

    def status(self, database: Path) -> CatalogueUpdateStatus:
        if not self.enabled:
            local = read_local_snapshot(database)
            return CatalogueUpdateStatus(False, "not_configured", local.catalogue_version if local else None)
        remote = self.fetch_snapshot()
        local = read_local_snapshot(database)
        if local and local.catalogue_version == remote.catalogue_version and local.sha256 == remote.sha256:
            return CatalogueUpdateStatus(True, "up_to_date", local.catalogue_version, remote.catalogue_version, remote.generated_at)
        return CatalogueUpdateStatus(
            True,
            "update_available",
            local.catalogue_version if local else None,
            remote.catalogue_version,
            remote.generated_at,
        )

    def stage_snapshot(self, snapshot: CatalogueSnapshot, directory: Path) -> Path:
        """Download, hash, and validate a snapshot without touching the live DB."""
        manifest_url = self._manifest_url()
        database_url = urljoin(manifest_url, snapshot.database_file)
        parsed = urlparse(database_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise CatalogueSnapshotError("Catalogue download must use an HTTPS release URL.")
        directory.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(prefix=".catalogue-update.", suffix=".part", dir=directory, delete=False) as handle:
            staged = Path(handle.name)
        try:
            with _client_context(self.client) as client:
                with client.stream("GET", database_url) as response:
                    response.raise_for_status()
                    response_url = urlparse(str(response.url))
                    if response_url.scheme != "https" or not response_url.netloc:
                        raise CatalogueSnapshotError("Catalogue update was redirected away from HTTPS.")
                    header_size = response.headers.get("Content-Length")
                    if header_size and (not header_size.isdecimal() or int(header_size) != snapshot.size_bytes):
                        raise CatalogueSnapshotError("Catalogue download size does not match its release metadata.")
                    written = 0
                    digest = sha256()
                    with staged.open("wb") as target:
                        for chunk in response.iter_bytes():
                            written += len(chunk)
                            if written > MAX_SNAPSHOT_BYTES:
                                raise CatalogueSnapshotError("Catalogue download is larger than the allowed limit.")
                            digest.update(chunk)
                            target.write(chunk)
            if written != snapshot.size_bytes or digest.hexdigest() != snapshot.sha256:
                raise CatalogueSnapshotError("Catalogue download does not match its release checksum.")
            validate_catalogue_database(staged)
            return staged
        except httpx.HTTPError as error:
            raise CatalogueSnapshotError("Could not download the published catalogue update.") from error
        except Exception:
            staged.unlink(missing_ok=True)
            raise


def replace_catalogue_atomically(staged_database: Path, database: Path, snapshot: CatalogueSnapshot) -> Path | None:
    """Install a staged database and retain one rollback copy until reopened."""
    backup = database.with_name(f"{database.name}.previous")
    database.parent.mkdir(parents=True, exist_ok=True)
    if backup.exists():
        backup.unlink()
    moved_existing = False
    try:
        if database.exists():
            os.replace(database, backup)
            moved_existing = True
        os.replace(staged_database, database)
        write_snapshot_manifest(local_version_path(database), snapshot)
    except Exception:
        if moved_existing and backup.exists() and not database.exists():
            os.replace(backup, database)
        raise
    return backup if moved_existing else None


def restore_previous_catalogue(database: Path, backup: Path | None) -> None:
    if backup and backup.exists():
        database.unlink(missing_ok=True)
        os.replace(backup, database)


def remove_catalogue_backup(backup: Path | None) -> None:
    if backup:
        backup.unlink(missing_ok=True)
