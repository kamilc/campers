"""Unit tests for CampersTUI."""

from unittest.mock import Mock, PropertyMock, patch

import pytest


@pytest.fixture
def tui_app():
    """Create CampersTUI instance with mocked dependencies.

    Returns
    -------
    Mock
        Mock CampersTUI instance for testing
    """
    from campers.tui.app import CampersTUI

    app = Mock(spec=CampersTUI)
    app.update_mutagen_status = CampersTUI.update_mutagen_status.__get__(app)

    return app


def test_update_mutagen_status_with_status_text_idle(tui_app):
    """Test update_mutagen_status displays 'File sync: idle' for idle status.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    from campers.tui.widgets.labeled_value import LabeledValue

    mock_widget = Mock(spec=LabeledValue)
    tui_app.query_one = Mock(return_value=mock_widget)

    tui_app.update_mutagen_status({"status_text": "idle"})

    tui_app.query_one.assert_called_once_with("#mutagen-widget", LabeledValue)
    assert mock_widget.value == "idle"


def test_update_mutagen_status_with_status_text_message(tui_app):
    """Test update_mutagen_status displays status_text message when not idle.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    from campers.tui.widgets.labeled_value import LabeledValue

    mock_widget = Mock(spec=LabeledValue)
    tui_app.query_one = Mock(return_value=mock_widget)

    status_msg = "Syncing: 42 files"
    tui_app.update_mutagen_status({"status_text": status_msg})

    assert mock_widget.value == status_msg


def test_update_mutagen_status_legacy_not_configured(tui_app):
    """Test backward compatibility with legacy 'not_configured' state.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    from campers.tui.widgets.labeled_value import LabeledValue

    mock_widget = Mock(spec=LabeledValue)
    tui_app.query_one = Mock(return_value=mock_widget)

    tui_app.update_mutagen_status({"state": "not_configured"})

    assert mock_widget.value == "Not syncing"


def test_update_mutagen_status_legacy_with_files_synced(tui_app):
    """Test backward compatibility with legacy state and files_synced.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    from campers.tui.widgets.labeled_value import LabeledValue

    mock_widget = Mock(spec=LabeledValue)
    tui_app.query_one = Mock(return_value=mock_widget)

    tui_app.update_mutagen_status({"state": "synced", "files_synced": 42})

    assert mock_widget.value == "synced (42 files)"


def test_update_mutagen_status_legacy_without_files_synced(tui_app):
    """Test backward compatibility with legacy state without files_synced.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    from campers.tui.widgets.labeled_value import LabeledValue

    mock_widget = Mock(spec=LabeledValue)
    tui_app.query_one = Mock(return_value=mock_widget)

    tui_app.update_mutagen_status({"state": "syncing"})

    assert mock_widget.value == "syncing"


def test_update_mutagen_status_legacy_unknown_state(tui_app):
    """Test backward compatibility with legacy missing state defaults to unknown.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    from campers.tui.widgets.labeled_value import LabeledValue

    mock_widget = Mock(spec=LabeledValue)
    tui_app.query_one = Mock(return_value=mock_widget)

    tui_app.update_mutagen_status({})

    assert mock_widget.value == "unknown"


def test_update_mutagen_status_widget_not_found(tui_app):
    """Test error handling when widget is not found.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    tui_app.query_one = Mock(side_effect=ValueError("Widget not found"))

    with patch("campers.tui.app.logging") as mock_logging:
        tui_app.update_mutagen_status({"status_text": "idle"})
        mock_logging.error.assert_called_once()


def test_update_mutagen_status_attribute_error(tui_app):
    """Test error handling when setting value raises AttributeError.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    from campers.tui.widgets.labeled_value import LabeledValue

    mock_widget = Mock(spec=LabeledValue)
    type(mock_widget).value = PropertyMock(side_effect=AttributeError("value property error"))
    tui_app.query_one = Mock(return_value=mock_widget)

    with patch("campers.tui.app.logging") as mock_logging:
        tui_app.update_mutagen_status({"status_text": "idle"})
        mock_logging.error.assert_called_once()


@pytest.fixture
def tui_app_for_public_ports():
    """Create CampersTUI instance for public ports testing.

    Returns
    -------
    Mock
        Mock CampersTUI instance for testing
    """
    from campers.tui.app import CampersTUI
    from campers.tui.widgets.labeled_value import LabeledValue

    app = Mock(spec=CampersTUI)
    app.update_from_config = CampersTUI.update_from_config.__get__(app)
    app.campers = Mock()
    app.campers._merged_config_prop = {}
    app.campers._resources = {}

    return app


def test_public_ports_widget_hidden_when_no_ports(tui_app_for_public_ports):
    """Test that public ports widget is hidden when public_ports is empty.

    Parameters
    ----------
    tui_app_for_public_ports : CampersTUI
        TUI app instance
    """
    mock_widget = Mock()
    tui_app_for_public_ports.query_one = Mock(return_value=mock_widget)

    tui_app_for_public_ports.update_from_config({"public_ports": []})

    mock_widget.add_class.assert_called_with("hidden")


def test_public_ports_widget_hidden_when_ports_missing(tui_app_for_public_ports):
    """Test that public ports widget is hidden when public_ports key is missing.

    Parameters
    ----------
    tui_app_for_public_ports : CampersTUI
        TUI app instance
    """
    mock_widget = Mock()
    tui_app_for_public_ports.query_one = Mock(return_value=mock_widget)

    tui_app_for_public_ports.update_from_config({})

    mock_widget.add_class.assert_called_with("hidden")


def test_public_ports_widget_shown_with_ip_and_urls(tui_app_for_public_ports):
    """Test that public ports widget shows public IP and URLs when ports configured.

    Parameters
    ----------
    tui_app_for_public_ports : CampersTUI
        TUI app instance
    """
    mock_widget = Mock()
    tui_app_for_public_ports.query_one = Mock(return_value=mock_widget)
    tui_app_for_public_ports.campers._resources = {"instance_details": {"public_ip": "192.0.2.1"}}

    tui_app_for_public_ports.update_from_config({"public_ports": [8080, 443]})

    mock_widget.update.assert_called_with(
        "Public IP: 192.0.2.1 | URLs: http://192.0.2.1:8080, https://192.0.2.1:443"
    )
    mock_widget.remove_class.assert_called_with("hidden")


def test_public_ports_widget_not_shown_without_public_ip(tui_app_for_public_ports):
    """Test that public ports widget stays hidden when no public IP available.

    Parameters
    ----------
    tui_app_for_public_ports : CampersTUI
        TUI app instance
    """
    public_ports_widget = Mock()
    other_widget = Mock()

    def query_one_side_effect(selector, *args):
        if "public-ports" in selector:
            return public_ports_widget
        return other_widget

    tui_app_for_public_ports.query_one = Mock(side_effect=query_one_side_effect)
    tui_app_for_public_ports.campers._resources = {"instance_details": {}}

    tui_app_for_public_ports.update_from_config({"public_ports": [8080]})

    public_ports_widget.update.assert_not_called()
    public_ports_widget.remove_class.assert_not_called()


@pytest.fixture
def tui_app_for_instance_details():
    """Create CampersTUI instance for instance details testing.

    Returns
    -------
    Mock
        Mock CampersTUI instance for testing
    """
    from campers.tui.app import CampersTUI

    app = Mock(spec=CampersTUI)
    app.update_from_instance_details = CampersTUI.update_from_instance_details.__get__(app)
    app.campers = Mock()
    app.campers._merged_config_prop = {}

    return app


def test_public_ports_widget_shown_on_instance_details_with_public_ip(
    tui_app_for_instance_details,
):
    """Test that public ports widget is shown when instance details include public IP.

    Parameters
    ----------
    tui_app_for_instance_details : CampersTUI
        TUI app instance
    """
    public_ports_widget = Mock()
    other_widget = Mock()

    def query_one_side_effect(selector, *args):
        if "public-ports" in selector:
            return public_ports_widget
        return other_widget

    tui_app_for_instance_details.query_one = Mock(side_effect=query_one_side_effect)
    tui_app_for_instance_details.campers._merged_config_prop = {"public_ports": [8888]}

    tui_app_for_instance_details.update_from_instance_details(
        {"public_ip": "52.29.99.159", "state": "running"}
    )

    public_ports_widget.update.assert_called_with(
        "Public IP: 52.29.99.159 | URLs: http://52.29.99.159:8888"
    )
    public_ports_widget.remove_class.assert_called_with("hidden")
