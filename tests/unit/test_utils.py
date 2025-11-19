"""Tests for moondock utility functions."""

import subprocess
from unittest.mock import MagicMock, patch


from moondock.utils import (
    generate_instance_name,
    get_git_branch,
    get_git_project_name,
    sanitize_instance_name,
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
        result = sanitize_instance_name("moondock-myproject-feature/new-api")
        assert result == "moondock-myproject-feature-new-api"

    def test_removes_invalid_characters(self) -> None:
        """Test removal of invalid characters."""
        result = sanitize_instance_name("moondock-myproject@v2#test")
        assert result == "moondock-myproject-v2-test"

    def test_removes_consecutive_dashes(self) -> None:
        """Test removal of consecutive dashes."""
        result = sanitize_instance_name("moondock--myproject---main")
        assert result == "moondock-myproject-main"

    def test_trims_leading_trailing_dashes(self) -> None:
        """Test trimming of leading and trailing dashes."""
        result = sanitize_instance_name("-moondock-myproject-main-")
        assert result == "moondock-myproject-main"

    def test_limits_to_256_characters(self) -> None:
        """Test limiting to 256 characters."""
        long_name = "a" * 300
        result = sanitize_instance_name(long_name)
        assert len(result) == 256

    def test_handles_special_characters_in_branch_name(self) -> None:
        """Test handling of special characters like @ and v."""
        result = sanitize_instance_name("moondock-myproject-feature/new-api@v2")
        assert result == "moondock-myproject-feature-new-api-v2"

    def test_handles_empty_after_sanitization(self) -> None:
        """Test handling of name that becomes empty after sanitization."""
        result = sanitize_instance_name("@#$%")
        assert result == ""


class TestGenerateInstanceName:
    """Tests for instance name generation."""

    def test_generates_git_based_name_with_branch(self) -> None:
        """Test generating name from git project and branch."""
        with (
            patch("moondock.utils.get_git_project_name") as mock_proj,
            patch("moondock.utils.get_git_branch") as mock_branch,
        ):
            mock_proj.return_value = "myproject"
            mock_branch.return_value = "main"
            result = generate_instance_name()
            assert result == "moondock-myproject-main"

    def test_generates_timestamp_name_without_branch(self) -> None:
        """Test fallback to timestamp when branch is None."""
        with (
            patch("moondock.utils.get_git_project_name") as mock_proj,
            patch("moondock.utils.get_git_branch") as mock_branch,
            patch("time.time") as mock_time,
        ):
            mock_proj.return_value = "myproject"
            mock_branch.return_value = None
            mock_time.return_value = 1234567890.5
            result = generate_instance_name()
            assert result == "moondock-1234567890"

    def test_generates_timestamp_name_without_project(self) -> None:
        """Test fallback to timestamp when project is None."""
        with (
            patch("moondock.utils.get_git_project_name") as mock_proj,
            patch("moondock.utils.get_git_branch") as mock_branch,
            patch("time.time") as mock_time,
        ):
            mock_proj.return_value = None
            mock_branch.return_value = "main"
            mock_time.return_value = 1234567890.5
            result = generate_instance_name()
            assert result == "moondock-1234567890"

    def test_sanitizes_git_based_name(self) -> None:
        """Test that git-based names are sanitized."""
        with (
            patch("moondock.utils.get_git_project_name") as mock_proj,
            patch("moondock.utils.get_git_branch") as mock_branch,
        ):
            mock_proj.return_value = "MyProject"
            mock_branch.return_value = "feature/new-api@v2"
            result = generate_instance_name()
            assert result == "moondock-myproject-feature-new-api-v2"

    def test_timestamp_is_10_digits(self) -> None:
        """Test that timestamp is 10 digits (Unix seconds)."""
        with (
            patch("moondock.utils.get_git_project_name") as mock_proj,
            patch("moondock.utils.get_git_branch") as mock_branch,
            patch("time.time") as mock_time,
        ):
            mock_proj.return_value = None
            mock_branch.return_value = None
            mock_time.return_value = 1234567890.5
            result = generate_instance_name()
            assert result.startswith("moondock-")
            timestamp_part = result.split("-")[1]
            assert len(timestamp_part) == 10
            assert timestamp_part.isdigit()
