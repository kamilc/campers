"""Unit tests for SelectableLog widget and Selection dataclass."""

from rich.text import Text

from campers.tui.widgets.selectable_log import SelectableLog
from campers.tui.widgets.selection import Selection


class TestSelection:
    """Tests for Selection dataclass."""

    def test_selection_creation(self) -> None:
        """Test creating a Selection."""
        selection = Selection(start=(0, 0), end=(1, 5))
        assert selection.start == (0, 0)
        assert selection.end == (1, 5)

    def test_selection_normalized_ascending(self) -> None:
        """Test normalized property when start is before end."""
        selection = Selection(start=(0, 0), end=(1, 5))
        start, end = selection.normalized
        assert start == (0, 0)
        assert end == (1, 5)

    def test_selection_normalized_descending(self) -> None:
        """Test normalized property when start is after end."""
        selection = Selection(start=(1, 5), end=(0, 0))
        start, end = selection.normalized
        assert start == (0, 0)
        assert end == (1, 5)

    def test_selection_normalized_same_line_ascending(self) -> None:
        """Test normalized property on same line with ascending columns."""
        selection = Selection(start=(0, 5), end=(0, 10))
        start, end = selection.normalized
        assert start == (0, 5)
        assert end == (0, 10)

    def test_selection_normalized_same_line_descending(self) -> None:
        """Test normalized property on same line with descending columns."""
        selection = Selection(start=(0, 10), end=(0, 5))
        start, end = selection.normalized
        assert start == (0, 5)
        assert end == (0, 10)


class TestSelectableLogBasic:
    """Tests for SelectableLog widget basic functionality."""

    def test_selectable_log_creation(self) -> None:
        """Test creating a SelectableLog widget."""
        log = SelectableLog(max_lines=1000)
        assert log.lines == []
        assert log.max_lines == 1000
        assert log.selection is None

    def test_selectable_log_default_max_lines(self) -> None:
        """Test SelectableLog uses default max_lines."""
        log = SelectableLog()
        assert log.max_lines == 5000

    def test_write_string_content(self) -> None:
        """Test writing string content to SelectableLog."""
        log = SelectableLog()
        log.write("Test line")
        assert len(log.lines) == 1
        assert log.lines[0].plain == "Test line"

    def test_write_rich_text_content(self) -> None:
        """Test writing Rich Text content to SelectableLog."""
        log = SelectableLog()
        text = Text("Styled text")
        log.write(text)
        assert len(log.lines) == 1
        assert log.lines[0].plain == "Styled text"

    def test_write_multiline_string(self) -> None:
        """Test writing multiline string content."""
        log = SelectableLog()
        log.write("Line 1\nLine 2\nLine 3")
        assert len(log.lines) == 3
        assert log.lines[0].plain == "Line 1"
        assert log.lines[1].plain == "Line 2"
        assert log.lines[2].plain == "Line 3"


class TestSelectableLogAnsi:
    """Tests for ANSI handling in SelectableLog."""

    def test_ansi_color_preserved(self) -> None:
        """Test ANSI color codes are converted to Rich styles."""
        log = SelectableLog()
        log.write("\x1b[31mRed text\x1b[0m")
        assert len(log.lines) == 1
        assert log.lines[0].plain == "Red text"

    def test_ansi_control_sequence_stripped(self) -> None:
        """Test ANSI control sequences are stripped."""
        log = SelectableLog()
        log.write("\x1b[2J\x1b[HClear screen")
        all_text = "".join([line.plain for line in log.lines])
        assert "\x1b[2J" not in all_text
        assert "\x1b[H" not in all_text

    def test_ansi_escape_char_not_visible(self) -> None:
        """Test escape character is not in plain text output."""
        log = SelectableLog()
        log.write("\x1b[31mColored\x1b[0m")
        all_text = "".join([line.plain for line in log.lines])
        assert "\x1b" not in all_text
        assert "\033" not in all_text


class TestSelectableLogBufferManagement:
    """Tests for buffer management in SelectableLog."""

    def test_buffer_trimming_exceeds_max_lines(self) -> None:
        """Test buffer is trimmed when exceeding max_lines."""
        log = SelectableLog(max_lines=5)
        for i in range(10):
            log.write(f"Line {i}")
        assert len(log.lines) == 5

    def test_buffer_trimming_keeps_last_lines(self) -> None:
        """Test trimmed buffer contains the last lines."""
        log = SelectableLog(max_lines=5)
        for i in range(10):
            log.write(f"Line {i}")
        assert log.lines[0].plain == "Line 5"
        assert log.lines[-1].plain == "Line 9"

    def test_buffer_no_trimming_below_max_lines(self) -> None:
        """Test buffer is not trimmed when below max_lines."""
        log = SelectableLog(max_lines=10)
        for i in range(5):
            log.write(f"Line {i}")
        assert len(log.lines) == 5

    def test_buffer_exact_max_lines(self) -> None:
        """Test buffer at exactly max_lines is not trimmed."""
        log = SelectableLog(max_lines=5)
        for i in range(5):
            log.write(f"Line {i}")
        assert len(log.lines) == 5

    def test_virtual_size_updated_after_write(self) -> None:
        """Test virtual_size is updated after writing."""
        log = SelectableLog()
        log.write("Short")
        width1, height1 = log.virtual_size
        assert height1 == 1

        log.write("Much longer line here")
        width2, height2 = log.virtual_size
        assert height2 == 2
        assert width2 >= 21

    def test_virtual_size_updated_after_trimming(self) -> None:
        """Test virtual_size is updated after buffer trimming."""
        log = SelectableLog(max_lines=3)
        for i in range(5):
            log.write(f"Line {i}")
        width, height = log.virtual_size
        assert height == 3


class TestSelectableLogSelection:
    """Tests for text selection in SelectableLog."""

    def test_get_selected_text_single_line(self) -> None:
        """Test getting selected text on a single line."""
        log = SelectableLog()
        log.write("Hello World")
        log.selection = Selection(start=(0, 0), end=(0, 5))
        assert log.get_selected_text() == "Hello"

    def test_get_selected_text_multiline(self) -> None:
        """Test getting selected text across multiple lines."""
        log = SelectableLog()
        log.write("Line 1\nLine 2\nLine 3")
        log.selection = Selection(start=(0, 3), end=(2, 4))
        expected = "e 1\nLine 2\nLine"
        assert log.get_selected_text() == expected

    def test_get_selected_text_no_selection(self) -> None:
        """Test getting selected text when no selection."""
        log = SelectableLog()
        log.write("Test content")
        assert log.get_selected_text() == ""

    def test_get_selected_text_reversed_selection(self) -> None:
        """Test getting selected text with reversed selection."""
        log = SelectableLog()
        log.write("Hello World")
        log.selection = Selection(start=(0, 5), end=(0, 0))
        assert log.get_selected_text() == "Hello"

    def test_get_selected_text_reversed_multiline(self) -> None:
        """Test getting selected text with reversed multiline selection."""
        log = SelectableLog()
        log.write("Line 1\nLine 2\nLine 3")
        log.selection = Selection(start=(2, 4), end=(0, 3))
        expected = "e 1\nLine 2\nLine"
        assert log.get_selected_text() == expected

    def test_get_selected_text_full_lines(self) -> None:
        """Test getting selected text for multiple full lines."""
        log = SelectableLog()
        log.write("Line 1\nLine 2\nLine 3")
        log.selection = Selection(start=(0, 0), end=(2, 6))
        expected = "Line 1\nLine 2\nLine 3"
        assert log.get_selected_text() == expected

    def test_get_selected_text_partial_first_last(self) -> None:
        """Test partial selection on first and last lines."""
        log = SelectableLog()
        log.write("First\nMiddle\nLast")
        log.selection = Selection(start=(0, 3), end=(2, 2))
        expected = "st\nMiddle\nLa"
        assert log.get_selected_text() == expected


class TestSelectableLogEmptyOperations:
    """Tests for operations on empty SelectableLog."""

    def test_get_selected_text_empty_log(self) -> None:
        """Test getting selected text from empty log."""
        log = SelectableLog()
        assert log.get_selected_text() == ""

    def test_selection_normalized_on_empty_log(self) -> None:
        """Test selection normalization doesn't crash on empty log."""
        selection = Selection(start=(0, 0), end=(1, 5))
        start, end = selection.normalized
        assert start == (0, 0)
        assert end == (1, 5)
