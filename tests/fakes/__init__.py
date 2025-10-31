"""Test fake implementations for dependency injection testing."""

from tests.fakes.fake_ec2_manager import FakeEC2Manager
from tests.fakes.fake_ssh_manager import FakeSSHManager

__all__ = ["FakeEC2Manager", "FakeSSHManager"]
