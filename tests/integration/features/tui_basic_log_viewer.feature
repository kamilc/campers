Feature: TUI Basic Log Viewer

@smoke @dry_run
Scenario: Running moondock run in interactive terminal launches TUI
  Given config file with defaults section
  And stdout is an interactive terminal
  When I run moondock command "run"
  Then TUI application launches
  And log messages are displayed in TUI

@smoke
Scenario: Running with --plain flag uses stderr logging
  Given config file with defaults section
  When I run moondock command "run --plain"
  Then TUI does not launch
  And logs are written to stderr

@smoke
Scenario: Running with --json-output flag uses JSON output
  Given config file with defaults section
  When I run moondock command "run --json-output"
  Then TUI does not launch
  And final output is JSON string to stdout

@smoke
Scenario: Running with MOONDOCK_TEST_MODE does not launch TUI
  Given MOONDOCK_TEST_MODE is "1"
  And config file with defaults section
  When I run moondock command "run"
  Then TUI does not launch
  And logs are written to stderr

@smoke
Scenario: Running in non-interactive shell does not launch TUI
  Given stdout is not a TTY
  And config file with defaults section
  When I run moondock command "run"
  Then TUI does not launch
  And logs are written to stderr

@smoke @dry_run
Scenario: Ctrl+C in TUI triggers graceful shutdown
  Given config file with defaults section
  And TUI application is running
  When SIGINT signal is received
  Then TUI begins graceful shutdown
  And TUI exits after cleanup

@smoke @dry_run
Scenario: Successful command completion in TUI mode
  Given config file with defaults section
  And TUI application is running
  When command execution completes successfully
  Then TUI displays success message
  And TUI exits automatically

@error @dry_run
Scenario: Failed command in TUI mode
  Given config file with defaults section
  And TUI application is running
  And command execution will fail
  When command execution completes
  Then TUI displays error messages
  And TUI exits automatically
