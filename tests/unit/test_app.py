"""Unit tests for CampersTUI."""

from unittest.mock import Mock, patch

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
    app.update_mutagen_status = CampersTUI.update_mutagen_status.__get__(
        app
    )

    return app


def test_update_mutagen_status_with_status_text_idle(tui_app):
    """Test update_mutagen_status displays 'File sync: idle' for idle status.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    mock_widget = Mock()
    tui_app.query_one = Mock(return_value=mock_widget)

    tui_app.update_mutagen_status({"status_text": "idle"})

    tui_app.query_one.assert_called_once_with("#mutagen-widget")
    mock_widget.update.assert_called_once_with("File sync: idle")


def test_update_mutagen_status_with_status_text_message(tui_app):
    """Test update_mutagen_status displays status_text message when not idle.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    mock_widget = Mock()
    tui_app.query_one = Mock(return_value=mock_widget)

    status_msg = "Syncing: 42 files"
    tui_app.update_mutagen_status({"status_text": status_msg})

    mock_widget.update.assert_called_once_with(f"File sync: {status_msg}")


def test_update_mutagen_status_legacy_not_configured(tui_app):
    """Test backward compatibility with legacy 'not_configured' state.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    mock_widget = Mock()
    tui_app.query_one = Mock(return_value=mock_widget)

    tui_app.update_mutagen_status({"state": "not_configured"})

    mock_widget.update.assert_called_once_with("File sync: Not syncing")


def test_update_mutagen_status_legacy_with_files_synced(tui_app):
    """Test backward compatibility with legacy state and files_synced.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    mock_widget = Mock()
    tui_app.query_one = Mock(return_value=mock_widget)

    tui_app.update_mutagen_status(
        {"state": "synced", "files_synced": 42}
    )

    mock_widget.update.assert_called_once_with(
        "File sync: synced (42 files)"
    )


def test_update_mutagen_status_legacy_without_files_synced(tui_app):
    """Test backward compatibility with legacy state without files_synced.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    mock_widget = Mock()
    tui_app.query_one = Mock(return_value=mock_widget)

    tui_app.update_mutagen_status({"state": "syncing"})

    mock_widget.update.assert_called_once_with("File sync: syncing")


def test_update_mutagen_status_legacy_unknown_state(tui_app):
    """Test backward compatibility with legacy missing state defaults to unknown.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    mock_widget = Mock()
    tui_app.query_one = Mock(return_value=mock_widget)

    tui_app.update_mutagen_status({})

    mock_widget.update.assert_called_once_with("File sync: unknown")


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
    """Test error handling when widget has no update method.

    Parameters
    ----------
    tui_app : CampersTUI
        TUI app instance
    """
    mock_widget = Mock(spec=[])
    tui_app.query_one = Mock(return_value=mock_widget)

    with patch("campers.tui.app.logging") as mock_logging:
        tui_app.update_mutagen_status({"status_text": "idle"})
        mock_logging.error.assert_called_once()
