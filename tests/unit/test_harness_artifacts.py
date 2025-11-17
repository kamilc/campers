"""Unit tests for ArtifactManager service."""

import shutil
from pathlib import Path

import pytest

from tests.harness.services.artifacts import ArtifactManager


@pytest.fixture
def temp_base_dir(tmp_path: Path) -> Path:
    """Create temporary base directory for artifacts."""
    base_dir = tmp_path / "artifacts"
    base_dir.mkdir()
    return base_dir


class TestArtifactManagerSetup:
    """Test artifact manager initialization."""

    def test_default_base_directory(self) -> None:
        """Test default base directory is tmp/behave."""
        manager = ArtifactManager()
        assert manager.base_dir == Path.cwd() / "tmp" / "behave"

    def test_custom_base_directory(self, temp_base_dir: Path) -> None:
        """Test setting custom base directory."""
        manager = ArtifactManager(base_dir=temp_base_dir)
        assert manager.base_dir == temp_base_dir


class TestArtifactManagerScenarioDir:
    """Test scenario directory creation."""

    def test_create_scenario_dir(self, temp_base_dir: Path) -> None:
        """Test creating scenario directory."""
        manager = ArtifactManager(base_dir=temp_base_dir)
        scenario_dir = manager.create_scenario_dir("test scenario")

        assert scenario_dir.exists()
        assert scenario_dir.parent.parent == temp_base_dir
        assert scenario_dir.parent.name == "test-scenario"

    def test_scenario_dir_sanitized(self, temp_base_dir: Path) -> None:
        """Test scenario name is sanitized."""
        manager = ArtifactManager(base_dir=temp_base_dir)
        scenario_dir = manager.create_scenario_dir("test scenario name")

        assert scenario_dir.parent.name == "test-scenario-name"

    def test_scenario_dir_normalized(self, temp_base_dir: Path) -> None:
        """Test scenario name with slashes is normalized."""
        manager = ArtifactManager(base_dir=temp_base_dir)
        scenario_dir = manager.create_scenario_dir("feature/test scenario")

        assert "/" not in scenario_dir.parent.name

    def test_scenario_dir_stored(self, temp_base_dir: Path) -> None:
        """Test scenario directory is stored in manager."""
        manager = ArtifactManager(base_dir=temp_base_dir)
        scenario_dir = manager.create_scenario_dir("test scenario")

        assert manager.scenario_dir == scenario_dir


class TestArtifactManagerTempFile:
    """Test temporary file creation."""

    def test_create_temp_file(self, temp_base_dir: Path) -> None:
        """Test creating temporary file."""
        manager = ArtifactManager(base_dir=temp_base_dir)
        manager.create_scenario_dir("test scenario")

        file_path = manager.create_temp_file("config.yaml", "key: value")

        assert file_path.exists()
        assert file_path.read_text() == "key: value"

    def test_create_temp_file_with_subdirs(self, temp_base_dir: Path) -> None:
        """Test creating temp file in subdirectories."""
        manager = ArtifactManager(base_dir=temp_base_dir)
        manager.create_scenario_dir("test scenario")

        file_path = manager.create_temp_file("subdir/config.yaml", "key: value")

        assert file_path.exists()
        assert file_path.parent.exists()

    def test_create_temp_file_without_scenario_dir_raises(
        self, temp_base_dir: Path
    ) -> None:
        """Test creating temp file without scenario dir raises."""
        manager = ArtifactManager(base_dir=temp_base_dir)

        with pytest.raises(RuntimeError):
            manager.create_temp_file("config.yaml")

    def test_create_temp_file_with_append_mode(self, temp_base_dir: Path) -> None:
        """Test creating temp file with append mode."""
        manager = ArtifactManager(base_dir=temp_base_dir)
        manager.create_scenario_dir("test scenario")

        manager.create_temp_file("test.txt", "line1\n")
        file_path = manager.create_temp_file("test.txt", "line2\n", mode="a")

        assert "line1" in file_path.read_text()
        assert "line2" in file_path.read_text()


class TestArtifactManagerCleanup:
    """Test cleanup behavior."""

    def test_cleanup_preserves_on_failure(self, temp_base_dir: Path) -> None:
        """Test cleanup preserves artifacts when preserve_on_failure=True."""
        manager = ArtifactManager(base_dir=temp_base_dir)
        scenario_dir = manager.create_scenario_dir("test scenario")

        manager.cleanup(preserve_on_failure=True)

        assert scenario_dir.exists()
        assert manager.run_id is not None
        assert manager.scenario_slug == "test-scenario"

    def test_cleanup_deletes_on_success(self, temp_base_dir: Path) -> None:
        """Test cleanup deletes artifacts when preserve_on_failure=False."""
        manager = ArtifactManager(base_dir=temp_base_dir)
        scenario_dir = manager.create_scenario_dir("test scenario")

        manager.cleanup(preserve_on_failure=False)

        assert not scenario_dir.exists()

    def test_cleanup_without_scenario_dir(self, temp_base_dir: Path) -> None:
        """Test cleanup without scenario dir doesn't raise."""
        manager = ArtifactManager(base_dir=temp_base_dir)
        manager.cleanup(preserve_on_failure=False)

    def test_cleanup_handles_missing_directory(self, temp_base_dir: Path) -> None:
        """Test cleanup handles already-deleted directory."""
        manager = ArtifactManager(base_dir=temp_base_dir)
        scenario_dir = manager.create_scenario_dir("test scenario")

        shutil.rmtree(scenario_dir)

        manager.cleanup(preserve_on_failure=False)
