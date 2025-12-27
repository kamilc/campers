Feature: Context Menu Widget

@smoke
Scenario: Context menu appears on right-click with selected text
  Given a SelectableLog widget with selected text "192.168.1.1"
  When user right-clicks on SelectableLog
  Then context menu is visible
  And menu has Copy, Search, Clear items
  And Copy menu item is enabled

@smoke
Scenario: Context menu adjusts position within viewport
  Given a SelectableLog widget with content "Test content"
  When user right-clicks near viewport edge
  Then context menu is adjusted within viewport
  And context menu is positioned within screen bounds

@smoke
Scenario: Copy action copies selected text to clipboard
  Given a SelectableLog widget with selected text "192.168.1.1"
  And context menu is open
  When user activates Copy from menu
  Then text is copied to clipboard
  And notification "Copied to clipboard" is shown
  And context menu closes

@smoke
Scenario: Copy action disabled when no text selected
  Given a SelectableLog widget with no selection
  And context menu is open
  Then Copy menu item is disabled
  And selecting Copy does nothing

@smoke
Scenario: Clear action removes all log content
  Given a SelectableLog widget with 10 lines of content
  And context menu is open
  When user activates Clear from menu
  Then widget displays no lines
  And context menu closes

@smoke
Scenario: Search action posts ContextMenuSearch message
  Given a SelectableLog widget with content "searchable"
  And context menu is open
  When user activates Search from menu
  Then ContextMenuSearch message is posted
  And context menu closes

@smoke
Scenario: Escape key closes context menu without action
  Given a SelectableLog widget with content "test"
  And context menu is open
  When user presses Escape
  Then context menu closes
  And no menu action is performed

@smoke
Scenario: Click outside menu closes context menu
  Given a SelectableLog widget with content "test"
  And context menu is open
  When user clicks outside the menu area
  Then context menu closes

@smoke
Scenario: Arrow keys navigate menu items
  Given a SelectableLog widget with content "test"
  And context menu is open with Copy highlighted
  When user presses Down arrow
  Then Search item is highlighted
  When user presses Down arrow
  Then Clear item is highlighted
  When user presses Down arrow
  Then Copy item is highlighted

@smoke
Scenario: Enter key activates highlighted menu item
  Given a SelectableLog widget with 5 lines of content
  And context menu is open with Clear highlighted
  When user presses Enter
  Then all content is cleared
  And context menu closes
