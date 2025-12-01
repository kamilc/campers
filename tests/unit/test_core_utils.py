"""Tests for campers.core.utils utility functions."""

from campers.core.utils import get_instance_id


class TestGetInstanceId:
    """Tests for get_instance_id function."""

    def test_returns_instance_id_when_present(self) -> None:
        """Test returns InstanceId when key is present."""
        instance_details = {"InstanceId": "i-1234567890abcdef0"}
        result = get_instance_id(instance_details)
        assert result == "i-1234567890abcdef0"

    def test_returns_lowercase_instance_id_as_fallback(self) -> None:
        """Test returns instance_id when InstanceId not present."""
        instance_details = {"instance_id": "i-0fedcba0987654321"}
        result = get_instance_id(instance_details)
        assert result == "i-0fedcba0987654321"

    def test_prefers_instance_id_over_fallback(self) -> None:
        """Test prefers InstanceId over instance_id when both present."""
        instance_details = {
            "InstanceId": "i-1234567890abcdef0",
            "instance_id": "i-0fedcba0987654321",
        }
        result = get_instance_id(instance_details)
        assert result == "i-1234567890abcdef0"

    def test_returns_empty_string_correctly(self) -> None:
        """Test returns empty string without falling back to instance_id."""
        instance_details = {"InstanceId": "", "instance_id": "i-fallback"}
        result = get_instance_id(instance_details)
        assert result == ""

    def test_returns_none_when_no_keys_present(self) -> None:
        """Test returns None when neither key is present."""
        instance_details = {}
        result = get_instance_id(instance_details)
        assert result is None

    def test_returns_none_when_both_values_none(self) -> None:
        """Test returns None when both keys have None values."""
        instance_details = {"InstanceId": None, "instance_id": None}
        result = get_instance_id(instance_details)
        assert result is None

    def test_handles_instance_id_with_hyphens(self) -> None:
        """Test handles instance ID with hyphens correctly."""
        instance_details = {"InstanceId": "i-abc-def-ghi"}
        result = get_instance_id(instance_details)
        assert result == "i-abc-def-ghi"

    def test_returns_zero_string(self) -> None:
        """Test returns zero as string without falling back."""
        instance_details = {"InstanceId": "0", "instance_id": "i-fallback"}
        result = get_instance_id(instance_details)
        assert result == "0"
