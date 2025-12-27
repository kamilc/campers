Feature: TUI SelectableLog Widget

@smoke
Scenario: SelectableLog widget renders log content
  Given a SelectableLog widget is created with max_lines 5000
  When text content "Test log line" is written
  Then the widget displays "Test log line"

@smoke
Scenario: ANSI color codes are preserved in output
  Given a SelectableLog widget is created with max_lines 5000
  When ANSI colored text "\x1b[31mError\x1b[0m" is written
  Then the text is displayed in red color
  And no raw escape characters are visible

@smoke
Scenario: ANSI control sequences are stripped
  Given a SelectableLog widget is created with max_lines 5000
  When ANSI control sequence "\x1b[2J\x1b[H" is written
  Then no control sequences are displayed
  And the widget renders without corruption

@smoke
Scenario: Buffer is trimmed when max_lines exceeded
  Given a SelectableLog widget is created with max_lines 10
  When 15 lines of text are written
  Then only the last 10 lines are stored
  And the first 5 lines are discarded

@smoke
Scenario: User can select text with mouse drag
  Given a SelectableLog widget with content "Line one" on line 0
  And the widget has focus
  When user clicks at position (0, 0)
  And user drags to position (0, 8)
  Then text is selected from column 0 to column 8
  And selection is visually highlighted

@smoke
Scenario: Ctrl+A selects all text
  Given a SelectableLog widget with content "First line"
  And the widget has focus
  When user presses Ctrl+A
  Then all content is selected
  And selection spans from start to end

@smoke
Scenario: Copy selected text with Ctrl+C
  Given a SelectableLog widget with selected text "192.168.1.1"
  When user presses Ctrl+C
  Then text is copied to clipboard
  And notification "Copied to clipboard" is shown

@smoke
Scenario: Auto-scroll to bottom on new content
  Given a SelectableLog widget is created with max_lines 5000
  And widget is scrolled to top
  When new content is written
  Then widget scrolls to show latest content
  And scroll position is at bottom

@smoke
Scenario: Ctrl+C bubbles when no text selected
  Given a SelectableLog widget with no selection
  And the widget has focus
  When user presses Ctrl+C
  Then key event bubbles to application
  And application quit handler receives event

@smoke
Scenario: TuiLogHandler integration
  Given a SelectableLog widget is mounted in TUI app
  When log message "Application started" is emitted
  Then message appears in SelectableLog widget
  And text can be selected and copied
