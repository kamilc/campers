"""Unit tests for environment.py SSH configuration functions."""

import tempfile
from pathlib import Path


from tests.integration.features.environment import (
    SSH_BLOCK_END,
    SSH_BLOCK_START,
    append_test_ssh_block,
    get_localhost_config_block,
    remove_test_ssh_block,
)


class TestGetLocalhostConfigBlock:
    """Tests for get_localhost_config_block function."""

    def test_returns_string(self) -> None:
        block = get_localhost_config_block()
        assert isinstance(block, str)

    def test_contains_start_marker(self) -> None:
        block = get_localhost_config_block()
        assert SSH_BLOCK_START in block

    def test_contains_end_marker(self) -> None:
        block = get_localhost_config_block()
        assert SSH_BLOCK_END in block

    def test_contains_host_localhost(self) -> None:
        block = get_localhost_config_block()
        assert "Host localhost" in block

    def test_contains_strict_host_key_checking(self) -> None:
        block = get_localhost_config_block()
        assert "StrictHostKeyChecking no" in block

    def test_contains_user_known_hosts_file(self) -> None:
        block = get_localhost_config_block()
        assert "UserKnownHostsFile=/dev/null" in block

    def test_markers_are_in_correct_order(self) -> None:
        block = get_localhost_config_block()
        start_pos = block.find(SSH_BLOCK_START)
        end_pos = block.find(SSH_BLOCK_END)
        assert start_pos < end_pos


class TestRemoveTestSshBlock:
    """Tests for remove_test_ssh_block function."""

    def test_handles_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nonexistent" / "config"
            remove_test_ssh_block(config_path)

    def test_removes_block_from_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            original_content = "Host myserver\n    User admin\n"
            block = get_localhost_config_block()
            config_path.write_text(original_content + block)

            remove_test_ssh_block(config_path)

            result = config_path.read_text()
            assert SSH_BLOCK_START not in result
            assert SSH_BLOCK_END not in result
            assert "Host myserver" in result

    def test_preserves_user_config_after_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            user_config = "Host production\n    User ubuntu\n"
            block = get_localhost_config_block()
            config_path.write_text(
                user_config + block + "Host staging\n    User admin\n"
            )

            remove_test_ssh_block(config_path)

            result = config_path.read_text()
            assert "Host production" in result
            assert "Host staging" in result
            assert SSH_BLOCK_START not in result
            assert SSH_BLOCK_END not in result

    def test_handles_multiple_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            block = get_localhost_config_block()
            config_path.write_text(block + "Other content\n" + block)

            remove_test_ssh_block(config_path)

            result = config_path.read_text()
            assert SSH_BLOCK_START not in result
            assert SSH_BLOCK_END not in result
            assert "Other content" in result

    def test_preserves_other_hosts_named_localhost(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            user_localhost = "Host localhost\n    ForwardAgent yes\n"
            block = get_localhost_config_block()
            config_path.write_text(user_localhost + block)

            remove_test_ssh_block(config_path)

            result = config_path.read_text()
            assert "Host localhost" in result
            assert "ForwardAgent yes" in result
            assert SSH_BLOCK_START not in result
            assert SSH_BLOCK_END not in result

    def test_idempotent_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            block = get_localhost_config_block()
            config_path.write_text("User content\n" + block)

            remove_test_ssh_block(config_path)
            first_result = config_path.read_text()

            remove_test_ssh_block(config_path)
            second_result = config_path.read_text()

            assert first_result == second_result

    def test_empty_config_after_block_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            block = get_localhost_config_block()
            config_path.write_text(block)

            remove_test_ssh_block(config_path)

            result = config_path.read_text()
            assert result.strip() == ""


class TestAppendTestSshBlock:
    """Tests for append_test_ssh_block function."""

    def test_creates_file_if_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            append_test_ssh_block(config_path)

            assert config_path.exists()

    def test_creates_directory_if_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".ssh" / "config"
            append_test_ssh_block(config_path)

            assert config_path.parent.exists()
            assert config_path.exists()

    def test_appends_to_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            config_path.write_text("")

            append_test_ssh_block(config_path)

            result = config_path.read_text()
            assert SSH_BLOCK_START in result
            assert SSH_BLOCK_END in result
            assert "Host localhost" in result

    def test_appends_to_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            user_config = "Host myserver\n    User admin\n"
            config_path.write_text(user_config)

            append_test_ssh_block(config_path)

            result = config_path.read_text()
            assert "Host myserver" in result
            assert SSH_BLOCK_START in result
            assert SSH_BLOCK_END in result

    def test_idempotent_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            append_test_ssh_block(config_path)
            first_result = config_path.read_text()

            append_test_ssh_block(config_path)
            second_result = config_path.read_text()

            assert first_result == second_result
            assert second_result.count(SSH_BLOCK_START) == 1
            assert second_result.count(SSH_BLOCK_END) == 1

    def test_replaces_existing_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            old_block = (
                f"\n{SSH_BLOCK_START}\nHost localhost\n"
                "    StrictHostKeyChecking yes\n"
                f"{SSH_BLOCK_END}\n"
            )
            config_path.write_text(old_block)

            append_test_ssh_block(config_path)

            result = config_path.read_text()
            assert "StrictHostKeyChecking no" in result
            assert result.count(SSH_BLOCK_START) == 1
            assert result.count(SSH_BLOCK_END) == 1

    def test_preserves_other_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            user_config = "Host prod\n    User ubuntu\nHost staging\n    User admin\n"
            config_path.write_text(user_config)

            append_test_ssh_block(config_path)

            result = config_path.read_text()
            assert "Host prod" in result
            assert "Host staging" in result
            assert "User ubuntu" in result
            assert "User admin" in result
            assert SSH_BLOCK_START in result
            assert SSH_BLOCK_END in result

    def test_full_cycle_append_remove(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            user_config = "Host original\n    User original_user\n"
            config_path.write_text(user_config)

            append_test_ssh_block(config_path)
            after_append = config_path.read_text()
            assert SSH_BLOCK_START in after_append

            remove_test_ssh_block(config_path)
            after_remove = config_path.read_text()

            assert "Host original" in after_remove
            assert SSH_BLOCK_START not in after_remove
            assert SSH_BLOCK_END not in after_remove
            assert after_remove.strip() == user_config.strip()

    def test_multiline_block_handling(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            existing_block = (
                f"\n{SSH_BLOCK_START}\nHost something\n"
                "    Line1\n"
                "    Line2\n"
                f"{SSH_BLOCK_END}\n"
            )
            config_path.write_text(existing_block)

            append_test_ssh_block(config_path)

            result = config_path.read_text()
            assert "Line1" not in result
            assert "Line2" not in result
            assert SSH_BLOCK_START in result
            assert SSH_BLOCK_END in result


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_lifecycle_write_read_write_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"

            append_test_ssh_block(config_path)
            assert SSH_BLOCK_START in config_path.read_text()

            append_test_ssh_block(config_path)
            content = config_path.read_text()
            assert content.count(SSH_BLOCK_START) == 1

            remove_test_ssh_block(config_path)
            final = config_path.read_text()
            assert SSH_BLOCK_START not in final
            assert SSH_BLOCK_END not in final

    def test_preserves_multiple_user_blocks_through_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config"
            user_blocks = (
                "Host server1\n    User alice\n\n"
                "Host server2\n    User bob\n\n"
                "Host server3\n    User charlie\n"
            )
            config_path.write_text(user_blocks)

            append_test_ssh_block(config_path)
            append_test_ssh_block(config_path)
            remove_test_ssh_block(config_path)

            result = config_path.read_text()
            assert "server1" in result
            assert "server2" in result
            assert "server3" in result
            assert "alice" in result
            assert "bob" in result
            assert "charlie" in result
            assert SSH_BLOCK_START not in result
