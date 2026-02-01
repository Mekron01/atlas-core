"""
Tests for FilesystemEye budget enforcement.

Tests that observation respects configured limits.
"""

import pytest

from atlas.eyes.filesystem import FilesystemEye
from atlas.ledger.writer import EventWriter


class SimpleBudget:
    """Simple budget object for testing."""

    def __init__(
        self,
        max_time_ms=None,
        max_files=None,
        max_bytes=None,
        max_depth=None,
    ):
        self.max_time_ms = max_time_ms
        self.max_files = max_files
        self.max_bytes = max_bytes
        self.max_depth = max_depth


class TestFilesystemEyeBudget:
    """Test FilesystemEye budget enforcement."""

    @pytest.fixture
    def temp_tree(self, tmp_path):
        """Create a temp directory tree for testing."""
        # Create structure:
        # tmp_path/
        #   file1.txt (100 bytes)
        #   file2.txt (100 bytes)
        #   subdir/
        #     file3.txt (100 bytes)
        #     deep/
        #       file4.txt (100 bytes)

        (tmp_path / "file1.txt").write_bytes(b"x" * 100)
        (tmp_path / "file2.txt").write_bytes(b"x" * 100)

        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_bytes(b"x" * 100)

        deep = subdir / "deep"
        deep.mkdir()
        (deep / "file4.txt").write_bytes(b"x" * 100)

        return tmp_path

    @pytest.fixture
    def writer(self, tmp_path):
        """Create event writer for testing."""
        ledger_dir = tmp_path / "ledger"
        return EventWriter(ledger_dir=str(ledger_dir))

    def test_observes_all_files_no_budget(self, temp_tree, writer):
        """Test all files observed without budget limits."""
        eye = FilesystemEye(writer)

        budget = SimpleBudget(
            max_files=1000,
            max_bytes=1_000_000,
            max_depth=10,
        )

        result = eye.observe(
            root=str(temp_tree),
            budget=budget,
            session_id="test-session",
        )

        assert result["files_seen"] == 4
        assert result["bytes_accounted"] == 400

    def test_max_files_limit(self, temp_tree, writer):
        """Test max_files budget is enforced."""
        eye = FilesystemEye(writer)

        budget = SimpleBudget(
            max_files=2,
            max_bytes=1_000_000,
            max_depth=10,
        )

        result = eye.observe(
            root=str(temp_tree),
            budget=budget,
            session_id="test-session",
        )

        assert result["files_seen"] == 2
        assert result["stopped_reason"] == "max_files"

    def test_max_bytes_limit(self, temp_tree, writer):
        """Test max_bytes budget is enforced."""
        eye = FilesystemEye(writer)

        budget = SimpleBudget(
            max_files=1000,
            max_bytes=250,  # Less than 4 files * 100 bytes
            max_depth=10,
        )

        result = eye.observe(
            root=str(temp_tree),
            budget=budget,
            session_id="test-session",
        )

        # Should stop after 2-3 files
        assert result["files_seen"] < 4
        assert result["stopped_reason"] == "max_bytes"

    def test_max_depth_limit(self, temp_tree, writer):
        """Test max_depth budget is enforced."""
        eye = FilesystemEye(writer)

        budget = SimpleBudget(
            max_files=1000,
            max_bytes=1_000_000,
            max_depth=1,  # Only top-level files
        )

        result = eye.observe(
            root=str(temp_tree),
            budget=budget,
            session_id="test-session",
        )

        # Should only see top-level files (file1.txt, file2.txt)
        assert result["files_seen"] == 2

    def test_zero_budget_stops_immediately(self, temp_tree, writer):
        """Test zero budget stops immediately."""
        eye = FilesystemEye(writer)

        budget = SimpleBudget(
            max_files=0,
            max_bytes=1_000_000,
            max_depth=10,
        )

        result = eye.observe(
            root=str(temp_tree),
            budget=budget,
            session_id="test-session",
        )

        assert result["files_seen"] == 0
        assert result["stopped_reason"] == "max_files"

    def test_no_files_returns_zero(self, tmp_path, writer):
        """Test empty directory returns zero files."""
        eye = FilesystemEye(writer)

        budget = SimpleBudget(
            max_files=1000,
            max_bytes=1_000_000,
            max_depth=10,
        )

        result = eye.observe(
            root=str(tmp_path),
            budget=budget,
            session_id="test-session",
        )

        assert result["files_seen"] == 0
        assert result["bytes_accounted"] == 0
