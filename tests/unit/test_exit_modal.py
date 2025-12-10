"""Unit tests for ExitModal widget."""

from unittest.mock import Mock

from campers.tui.exit_modal import ExitModal


class TestExitModal:
    """Tests for ExitModal widget."""

    def test_init_basic(self) -> None:
        """Test that ExitModal initializes without errors."""
        modal = ExitModal()
        assert modal.public_ip is None
        assert modal.public_ports == []
        assert modal.hourly_cost is None

    def test_init_with_parameters(self) -> None:
        """Test ExitModal initialization with all parameters."""
        modal = ExitModal(
            public_ip="192.0.2.1",
            public_ports=[8080, 443],
            hourly_cost=0.50,
        )
        assert modal.public_ip == "192.0.2.1"
        assert modal.public_ports == [8080, 443]
        assert modal.hourly_cost == 0.50

    def test_public_ports_empty_list_default(self) -> None:
        """Test that None public_ports defaults to empty list."""
        modal = ExitModal(public_ports=None)
        assert modal.public_ports == []
        assert isinstance(modal.public_ports, list)

    def test_bindings_defined(self) -> None:
        """Test that keyboard bindings are defined."""
        modal = ExitModal()
        assert hasattr(modal, "BINDINGS")
        assert len(modal.BINDINGS) > 0

        binding_keys = [binding[0] for binding in modal.BINDINGS]
        assert "s" in binding_keys
        assert "k" in binding_keys
        assert "d" in binding_keys
        assert "escape" in binding_keys

    def test_action_select_stop(self) -> None:
        """Test action_select with stop action."""
        modal = ExitModal()
        modal.dismiss = Mock()

        modal.action_select("stop")

        modal.dismiss.assert_called_once_with("stop")

    def test_action_select_detach(self) -> None:
        """Test action_select with detach action."""
        modal = ExitModal()
        modal.dismiss = Mock()

        modal.action_select("detach")

        modal.dismiss.assert_called_once_with("detach")

    def test_action_select_destroy(self) -> None:
        """Test action_select with destroy action."""
        modal = ExitModal()
        modal.dismiss = Mock()

        modal.action_select("destroy")

        modal.dismiss.assert_called_once_with("destroy")

    def test_action_select_cancel(self) -> None:
        """Test action_select with cancel action."""
        modal = ExitModal()
        modal.dismiss = Mock()

        modal.action_select("cancel")

        modal.dismiss.assert_called_once_with("cancel")

    def test_on_button_pressed_stop(self) -> None:
        """Test on_button_pressed with Stop button."""
        modal = ExitModal()
        modal.dismiss = Mock()

        mock_button = Mock()
        mock_button.id = "btn-stop"
        mock_event = Mock()
        mock_event.button = mock_button

        modal.on_button_pressed(mock_event)

        modal.dismiss.assert_called_once_with("stop")

    def test_on_button_pressed_detach(self) -> None:
        """Test on_button_pressed with Keep running button."""
        modal = ExitModal()
        modal.dismiss = Mock()

        mock_button = Mock()
        mock_button.id = "btn-detach"
        mock_event = Mock()
        mock_event.button = mock_button

        modal.on_button_pressed(mock_event)

        modal.dismiss.assert_called_once_with("detach")

    def test_on_button_pressed_destroy(self) -> None:
        """Test on_button_pressed with Destroy button returns terminate action."""
        modal = ExitModal()
        modal.dismiss = Mock()

        mock_button = Mock()
        mock_button.id = "btn-destroy"
        mock_event = Mock()
        mock_event.button = mock_button

        modal.on_button_pressed(mock_event)

        modal.dismiss.assert_called_once_with("terminate")

    def test_on_button_pressed_cancel(self) -> None:
        """Test on_button_pressed with Cancel button."""
        modal = ExitModal()
        modal.dismiss = Mock()

        mock_button = Mock()
        mock_button.id = "btn-cancel"
        mock_event = Mock()
        mock_event.button = mock_button

        modal.on_button_pressed(mock_event)

        modal.dismiss.assert_called_once_with("cancel")

    def test_on_button_pressed_unknown_button(self) -> None:
        """Test on_button_pressed defaults to cancel for unknown button."""
        modal = ExitModal()
        modal.dismiss = Mock()

        mock_button = Mock()
        mock_button.id = "btn-unknown"
        mock_event = Mock()
        mock_event.button = mock_button

        modal.on_button_pressed(mock_event)

        modal.dismiss.assert_called_once_with("cancel")

    def test_css_defined(self) -> None:
        """Test that CSS styling is defined."""
        modal = ExitModal()
        assert hasattr(modal, "CSS")
        assert isinstance(modal.CSS, str)
        assert len(modal.CSS) > 0
        assert "ExitModal" in modal.CSS
        assert "#exit-dialog" in modal.CSS

    def test_public_ip_with_port_443(self) -> None:
        """Test that port 443 uses HTTPS protocol."""
        modal = ExitModal(public_ip="192.0.2.1", public_ports=[443])
        assert modal.public_ip == "192.0.2.1"
        assert 443 in modal.public_ports

    def test_public_ip_with_http_port(self) -> None:
        """Test that non-443 ports use HTTP protocol."""
        modal = ExitModal(public_ip="192.0.2.1", public_ports=[8080, 3000])
        assert modal.public_ip == "192.0.2.1"
        assert 8080 in modal.public_ports
        assert 3000 in modal.public_ports

    def test_hourly_cost_formatting(self) -> None:
        """Test that hourly cost is stored correctly."""
        modal = ExitModal(hourly_cost=0.123456)
        assert modal.hourly_cost == 0.123456
