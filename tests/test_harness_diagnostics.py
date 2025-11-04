"""Unit tests for DiagnosticsCollector service."""

import time


from tests.harness.services.diagnostics import DiagnosticEvent, DiagnosticsCollector


class TestDiagnosticEvent:
    """Test DiagnosticEvent dataclass."""

    def test_create_event_with_all_fields(self) -> None:
        """Test creating event with all fields."""
        event = DiagnosticEvent(
            event_type="test-type",
            description="test description",
            details={"key": "value"},
        )

        assert event.event_type == "test-type"
        assert event.description == "test description"
        assert event.details == {"key": "value"}
        assert event.timestamp > 0

    def test_create_event_with_minimal_fields(self) -> None:
        """Test creating event with minimal fields."""
        event = DiagnosticEvent(
            event_type="test-type",
            description="test description",
        )

        assert event.event_type == "test-type"
        assert event.description == "test description"
        assert event.details == {}
        assert event.timestamp > 0


class TestDiagnosticsCollectorRecord:
    """Test recording diagnostic events."""

    def test_record_event(self) -> None:
        """Test recording a single event."""
        collector = DiagnosticsCollector()
        collector.record("test-type", "test description")

        assert len(collector.events) == 1
        assert collector.events[0].event_type == "test-type"

    def test_record_event_with_details(self) -> None:
        """Test recording event with details."""
        collector = DiagnosticsCollector()
        details = {"resource": "test", "status": "active"}
        collector.record("test-type", "test description", details)

        assert collector.events[0].details == details

    def test_record_multiple_events(self) -> None:
        """Test recording multiple events."""
        collector = DiagnosticsCollector()

        collector.record("type1", "desc1")
        collector.record("type2", "desc2")
        collector.record("type3", "desc3")

        assert len(collector.events) == 3

    def test_record_preserves_order(self) -> None:
        """Test events are recorded in order."""
        collector = DiagnosticsCollector()

        collector.record("first", "first event")
        time.sleep(0.01)
        collector.record("second", "second event")
        time.sleep(0.01)
        collector.record("third", "third event")

        assert collector.events[0].event_type == "first"
        assert collector.events[1].event_type == "second"
        assert collector.events[2].event_type == "third"


class TestDiagnosticsCollectorClear:
    """Test clearing events."""

    def test_clear_removes_all_events(self) -> None:
        """Test clear removes all events."""
        collector = DiagnosticsCollector()

        collector.record("type1", "desc1")
        collector.record("type2", "desc2")

        assert len(collector.events) == 2

        collector.clear()

        assert len(collector.events) == 0

    def test_clear_empty_collector(self) -> None:
        """Test clear on empty collector."""
        collector = DiagnosticsCollector()
        collector.clear()
        assert len(collector.events) == 0


class TestDiagnosticsCollectorFilter:
    """Test filtering events by type."""

    def test_get_events_by_type(self) -> None:
        """Test filtering events by type."""
        collector = DiagnosticsCollector()

        collector.record("resource", "resource1")
        collector.record("timeout", "timeout1")
        collector.record("resource", "resource2")
        collector.record("signal", "signal1")
        collector.record("resource", "resource3")

        resource_events = collector.get_events_by_type("resource")

        assert len(resource_events) == 3
        assert all(e.event_type == "resource" for e in resource_events)

    def test_get_events_by_nonexistent_type(self) -> None:
        """Test filtering by non-existent type returns empty list."""
        collector = DiagnosticsCollector()

        collector.record("type1", "desc1")
        collector.record("type2", "desc2")

        result = collector.get_events_by_type("nonexistent")

        assert result == []

    def test_get_events_preserves_order(self) -> None:
        """Test filtered events preserve original order."""
        collector = DiagnosticsCollector()

        collector.record("resource", "first")
        collector.record("other", "other")
        collector.record("resource", "second")
        collector.record("other", "other")
        collector.record("resource", "third")

        resource_events = collector.get_events_by_type("resource")

        assert [e.description for e in resource_events] == ["first", "second", "third"]


class TestDiagnosticsCollectorVerbose:
    """Test verbose mode."""

    def test_create_verbose_collector(self) -> None:
        """Test creating collector with verbose=True."""
        collector = DiagnosticsCollector(verbose=True)
        assert collector.verbose is True

    def test_create_quiet_collector(self) -> None:
        """Test creating collector with verbose=False."""
        collector = DiagnosticsCollector(verbose=False)
        assert collector.verbose is False

    def test_verbose_default_false(self) -> None:
        """Test verbose defaults to False."""
        collector = DiagnosticsCollector()
        assert collector.verbose is False
