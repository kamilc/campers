Feature: TUI Vim-like Search

@smoke
Scenario: Search opens with slash key
  Given a SelectableLog widget with content "error line"
  And the widget has focus
  When user presses "/" key
  Then search input appears
  And search input has focus

@smoke
Scenario: Search opens with Ctrl+F
  Given a SelectableLog widget with content "warning line"
  And the widget has focus
  When user presses "Ctrl+F" key
  Then search input appears
  And search input has focus

@smoke
Scenario: Search opens from context menu
  Given a SelectableLog widget with content "debug line"
  And context menu is open
  When user activates Search from menu
  Then search input appears
  And search input has focus

@smoke
Scenario: Matches are highlighted as user types
  Given a SelectableLog widget with content "error" on line 0
  And a SelectableLog widget with content "error" on line 5
  And search input is open
  When user types "error"
  Then 2 matches are found
  And match count shows "1 of 2"

@smoke
Scenario: Current match has distinct highlighting
  Given a SelectableLog widget with 3 lines of content containing "warning"
  And search is active with "warning" query
  Then first match is highlighted with orange
  And other matches are highlighted with yellow

@smoke
Scenario: Navigate to next match with n key
  Given a SelectableLog widget with matches at lines 0 and 5
  And search is active with current match at line 0
  When user presses "n" key
  Then current match changes to line 5

@smoke
Scenario: Navigate to previous match with N key
  Given a SelectableLog widget with matches at lines 0 and 5
  And search is active with current match at line 5
  When user presses "N" key
  Then current match changes to line 0

@smoke
Scenario: Match navigation wraps around
  Given a SelectableLog widget with matches at lines 0 and 5
  And search is active with current match at line 5
  When user presses "n" key
  Then current match wraps to line 0

@smoke
Scenario: Escape closes search and clears highlighting
  Given a SelectableLog widget with active search
  And matches are highlighted
  When user presses "Escape" key
  Then search input closes
  And all match highlighting is removed

@smoke
Scenario: Enter closes search but preserves highlighting
  Given a SelectableLog widget with active search
  And matches are highlighted
  When user presses "Enter" key
  Then search input closes
  And match highlighting remains visible

@smoke
Scenario: No matches displays appropriate message
  Given a SelectableLog widget with content "hello world"
  And search input is open
  When user types "xyz"
  Then match count shows "No matches"

@smoke
Scenario: Search is case-insensitive
  Given a SelectableLog widget with content "Error"
  And a SelectableLog widget with content "ERROR"
  And a SelectableLog widget with content "error"
  And search input is open
  When user types "error"
  Then 3 matches are found

@smoke
Scenario: Special characters are searched literally
  Given a SelectableLog widget with content "[a-z]+"
  And search input is open
  When user types "[a-z]+"
  Then 1 match is found

@smoke
Scenario: F3 navigates to next match
  Given a SelectableLog widget with active search
  And current match is at index 0
  When user presses "F3" key
  Then current match advances to index 1

@smoke
Scenario: Shift+F3 navigates to previous match
  Given a SelectableLog widget with active search
  And current match is at index 1
  When user presses "Shift+F3" key
  Then current match moves back to index 0
