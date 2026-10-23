"""Unit tests for DownloadManager."""

import tempfile
from pathlib import Path
import pytest
from food_engine.data_ingestion.download_manager import DownloadManager, DiskSpaceError


def test_download_manager_init():
    with tempfile.TemporaryDirectory() as tmpdir:
        dm = DownloadManager(repo_root=Path(tmpdir))
        assert dm.manifest_path.exists()
        manifest = dm._load_manifest()
        assert "downloads" in manifest


def test_disk_space_check():
    with tempfile.TemporaryDirectory() as tmpdir:
        dm = DownloadManager(repo_root=Path(tmpdir))
        # Checking realistic 1 MB required should pass
        dm.check_disk_space(Path(tmpdir), required_bytes=1024 * 1024, safety_margin_gb=0.1)

        # Checking absurdly huge requirement (e.g. 50,000 GB) should raise DiskSpaceError
        with pytest.raises(DiskSpaceError):
            dm.check_disk_space(Path(tmpdir), required_bytes=50_000 * (1024**3), safety_margin_gb=1.0)


def test_sha256_calculation():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_bytes(b"food-intelligence-engine-test-bytes")
        sha = DownloadManager.calculate_sha256(test_file)
        assert len(sha) == 64
        # Known SHA256 of b"food-intelligence-engine-test-bytes"
        import hashlib
        expected = hashlib.sha256(b"food-intelligence-engine-test-bytes").hexdigest()
        assert sha == expected
