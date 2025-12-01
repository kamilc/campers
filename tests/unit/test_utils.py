"""Tests for campers utility functions."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from campers.providers.aws.utils import (
    extract_instance_from_response,
    sanitize_instance_name,
)
from campers.services.validation import validate_port
from campers.utils import (
    atomic_file_write,
    generate_instance_name,
    get_git_branch,
    get_git_project_name,
)


class TestGetGitProjectName:
    """Tests for git project name detection."""

    def test_extracts_project_from_https_url(self) -> None:
        """Test extracting project name from HTTPS git URL."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="https://github.com/user/myproject.git\n"
            )
            result = get_git_project_name()
            assert result == "myproject"
            mock_run.assert_called_once()

    def test_extracts_project_from_ssh_url(self) -> None:
        """Test extracting project name from SSH git URL."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="git@github.com:user/myproject.git\n"
            )
            result = get_git_project_name()
            assert result == "myproject"

    def test_handles_git_not_found(self) -> None:
        """Test fallback when git command not found."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            with patch("os.path.basename") as mock_basename:
                mock_basename.return_value = "fallback-dir"
                result = get_git_project_name()
                assert result == "fallback-dir"

    def test_handles_timeout(self) -> None:
        """Test fallback when git command times out."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 2)
            with patch("os.path.basename") as mock_basename:
                mock_basename.return_value = "fallback-dir"
                result = get_git_project_name()
                assert result == "fallback-dir"

    def test_handles_nonzero_return_code(self) -> None:
        """Test fallback when git command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            with patch("os.path.basename") as mock_basename:
                mock_basename.return_value = "fallback-dir"
                result = get_git_project_name()
                assert result == "fallback-dir"


class TestGetGitBranch:
    """Tests for git branch detection."""

    def test_returns_branch_name(self) -> None:
        """Test extracting branch name."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="main\n")
            result = get_git_branch()
            assert result == "main"

    def test_returns_feature_branch(self) -> None:
        """Test extracting feature branch name."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="feature/new-api\n")
            result = get_git_branch()
            assert result == "feature/new-api"

    def test_returns_none_for_detached_head(self) -> None:
        """Test returns None for detached HEAD state."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="HEAD\n")
            result = get_git_branch()
            assert result is None

    def test_returns_none_for_git_not_found(self) -> None:
        """Test returns None when git command not found."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = get_git_branch()
            assert result is None

    def test_returns_none_for_timeout(self) -> None:
        """Test returns None when git command times out."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 2)
            result = get_git_branch()
            assert result is None

    def test_returns_none_for_nonzero_return_code(self) -> None:
        """Test returns None when git command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = get_git_branch()
            assert result is None


class TestSanitizeInstanceName:
    """Tests for instance name sanitization."""

    def test_converts_to_lowercase(self) -> None:
        """Test conversion to lowercase."""
        result = sanitize_instance_name("MyProject-Main")
        assert result == "myproject-main"

    def test_replaces_forward_slashes(self) -> None:
        """Test replacement of forward slashes with dashes."""
        result = sanitize_instance_name("campers-myproject-feature/new-api")
        assert result == "campers-myproject-feature-new-api"

    def test_removes_invalid_characters(self) -> None:
        """Test removal of invalid characters."""
        result = sanitize_instance_name("campers-myproject@v2#test")
        assert result == "campers-myproject-v2-test"

    def test_removes_consecutive_dashes(self) -> None:
        """Test removal of consecutive dashes."""
        result = sanitize_instance_name("campers--myproject---main")
        assert result == "campers-myproject-main"

    def test_trims_leading_trailing_dashes(self) -> None:
        """Test trimming of leading and trailing dashes."""
        result = sanitize_instance_name("-campers-myproject-main-")
        assert result == "campers-myproject-main"

    def test_limits_to_256_characters(self) -> None:
        """Test limiting to 256 characters."""
        long_name = "a" * 300
        result = sanitize_instance_name(long_name)
        assert len(result) == 256

    def test_handles_special_characters_in_branch_name(self) -> None:
        """Test handling of special characters like @ and v."""
        result = sanitize_instance_name("campers-myproject-feature/new-api@v2")
        assert result == "campers-myproject-feature-new-api-v2"

    def test_handles_empty_after_sanitization(self) -> None:
        """Test handling of name that becomes empty after sanitization."""
        result = sanitize_instance_name("@#$%")
        assert result == ""


class TestGenerateInstanceName:
    """Tests for instance name generation."""

    def test_generates_git_based_name_with_branch(self) -> None:
        """Test generating name from git project and branch."""
        with (
            patch("campers.utils.get_git_project_name") as mock_proj,
            patch("campers.utils.get_git_branch") as mock_branch,
        ):
            mock_proj.return_value = "myproject"
            mock_branch.return_value = "main"
            result = generate_instance_name()
            assert result == "campers-myproject-main"

    def test_generates_timestamp_name_without_branch(self) -> None:
        """Test fallback to timestamp when branch is None."""
        with (
            patch("campers.utils.get_git_project_name") as mock_proj,
            patch("campers.utils.get_git_branch") as mock_branch,
            patch("time.time") as mock_time,
        ):
            mock_proj.return_value = "myproject"
            mock_branch.return_value = None
            mock_time.return_value = 1234567890.5
            result = generate_instance_name()
            assert result == "campers-1234567890500000"

    def test_generates_timestamp_name_without_project(self) -> None:
        """Test fallback to timestamp when project is None."""
        with (
            patch("campers.utils.get_git_project_name") as mock_proj,
            patch("campers.utils.get_git_branch") as mock_branch,
            patch("time.time") as mock_time,
        ):
            mock_proj.return_value = None
            mock_branch.return_value = "main"
            mock_time.return_value = 1234567890.5
            result = generate_instance_name()
            assert result == "campers-1234567890500000"

    def test_sanitizes_git_based_name(self) -> None:
        """Test that git-based names are sanitized."""
        with (
            patch("campers.utils.get_git_project_name") as mock_proj,
            patch("campers.utils.get_git_branch") as mock_branch,
        ):
            mock_proj.return_value = "MyProject"
            mock_branch.return_value = "feature/new-api@v2"
            result = generate_instance_name()
            assert result == "campers-myproject-feature-new-api-v2"

    def test_timestamp_is_10_digits(self) -> None:
        """Test that timestamp is 16 digits (Unix microseconds)."""
        with (
            patch("campers.utils.get_git_project_name") as mock_proj,
            patch("campers.utils.get_git_branch") as mock_branch,
            patch("time.time") as mock_time,
        ):
            mock_proj.return_value = None
            mock_branch.return_value = None
            mock_time.return_value = 1234567890.5
            result = generate_instance_name()
            assert result.startswith("campers-")
            timestamp_part = result.split("-")[1]
            assert len(timestamp_part) == 16
            assert timestamp_part.isdigit()


class TestExtractInstanceFromResponse:
    """Tests for instance extraction from AWS response."""

    def test_extracts_first_instance(self) -> None:
        """Test normal extraction of first instance."""
        response = {
            "Reservations": [
                {
                    "Instances": [
                        {"InstanceId": "i-123456", "State": {"Name": "running"}},
                        {"InstanceId": "i-789012", "State": {"Name": "running"}},
                    ]
                }
            ]
        }
        result = extract_instance_from_response(response)
        assert result["InstanceId"] == "i-123456"

    def test_raises_on_no_reservations(self) -> None:
        """Test ValueError when no reservations in response."""
        response = {"Reservations": []}
        with pytest.raises(ValueError, match="No reservations"):
            extract_instance_from_response(response)

    def test_raises_on_missing_reservations_key(self) -> None:
        """Test ValueError when Reservations key missing."""
        response = {}
        with pytest.raises(ValueError, match="No reservations"):
            extract_instance_from_response(response)

    def test_raises_on_no_instances(self) -> None:
        """Test ValueError when no instances in reservation."""
        response = {"Reservations": [{"Instances": []}]}
        with pytest.raises(ValueError, match="No instances"):
            extract_instance_from_response(response)

    def test_raises_on_missing_instances_key(self) -> None:
        """Test ValueError when Instances key missing."""
        response = {"Reservations": [{}]}
        with pytest.raises(ValueError, match="No instances"):
            extract_instance_from_response(response)


class TestValidatePort:
    """Tests for port validation."""

    def test_accepts_valid_port_8080(self) -> None:
        """Test accepts valid port 8080."""
        validate_port(8080)

    def test_accepts_minimum_valid_port(self) -> None:
        """Test accepts minimum valid port 1."""
        validate_port(1)

    def test_accepts_maximum_valid_port(self) -> None:
        """Test accepts maximum valid port 65535."""
        validate_port(65535)

    def test_rejects_port_zero(self) -> None:
        """Test rejects port 0."""
        with pytest.raises(ValueError, match="Port must be between"):
            validate_port(0)

    def test_rejects_negative_port(self) -> None:
        """Test rejects negative port."""
        with pytest.raises(ValueError, match="Port must be between"):
            validate_port(-1)

    def test_rejects_port_over_65535(self) -> None:
        """Test rejects port exceeding 65535."""
        with pytest.raises(ValueError, match="Port must be between"):
            validate_port(65536)

    def test_rejects_string_port(self) -> None:
        """Test rejects non-integer port."""
        with pytest.raises(ValueError, match="Port must be an integer"):
            validate_port("8080")  # type: ignore

    def test_rejects_float_port(self) -> None:
        """Test rejects float port."""
        with pytest.raises(ValueError, match="Port must be an integer"):
            validate_port(8080.5)  # type: ignore


class TestAtomicFileWrite:
    """Tests for atomic file write operations."""

    def test_writes_file_atomically(self) -> None:
        """Test successful atomic write."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test.txt"
            content = "test content"

            atomic_file_write(target_path, content)

            assert target_path.exists()
            assert target_path.read_text() == content

    def test_no_temp_file_after_success(self) -> None:
        """Test temp file is cleaned up after success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test.txt"
            content = "test content"

            atomic_file_write(target_path, content)

            temp_path = target_path.with_suffix(".tmp")
            assert not temp_path.exists()

    def test_overwrites_existing_file(self) -> None:
        """Test overwrites existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test.txt"
            target_path.write_text("old content")

            new_content = "new content"
            atomic_file_write(target_path, new_content)

            assert target_path.read_text() == new_content

    def test_cleans_up_temp_file_on_write_failure(self) -> None:
        """Test temp file cleanup on write failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test.txt"

            with patch("builtins.open", side_effect=OSError("Write failed")):
                with pytest.raises(IOError):
                    atomic_file_write(target_path, "content")

            temp_path = target_path.with_suffix(".tmp")
            assert not temp_path.exists()

    def test_preserves_exception_on_failure(self) -> None:
        """Test original exception is preserved on failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test.txt"

            with patch("builtins.open", side_effect=OSError("Write failed")):
                with pytest.raises(IOError, match="Write failed"):
                    atomic_file_write(target_path, "content")

    def test_writes_empty_file(self) -> None:
        """Test writes empty content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test.txt"

            atomic_file_write(target_path, "")

            assert target_path.exists()
            assert target_path.read_text() == ""

    def test_writes_large_content(self) -> None:
        """Test writes large content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test.txt"
            large_content = "x" * (10 * 1024 * 1024)

            atomic_file_write(target_path, large_content)

            assert target_path.read_text() == large_content

    def test_writes_content_with_special_chars(self) -> None:
        """Test writes content with special characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test.txt"
            content = "line1\nline2\ttab\nspecial chars: !@#$%^&*()"

            atomic_file_write(target_path, content)

            assert target_path.read_text() == content
