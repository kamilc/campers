Feature: Campers CLI Execution

@smoke
Scenario: Execute CLI with help flag
  When I run "uv run -m campers --help"
  Then exit code is 0
  And output contains "campers"

@smoke
Scenario: Fire CLI routing
  When I run "uv run -m campers --help"
  Then exit code is 0
  And output contains "campers"
