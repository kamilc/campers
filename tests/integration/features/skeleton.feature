Feature: Moondock CLI Execution

@smoke
Scenario: Execute CLI with help flag
  Given campers.py exists in project root
  And campers.py contains PEP 723 dependencies
  When I run "uv run -m campers --help"
  Then exit code is 0
  And output contains "campers"

@smoke
Scenario: Verify dependency installation
  Given campers.py exists in project root
  And campers.py contains dependency "boto3>=1.40.0"
  And campers.py contains dependency "PyYAML>=6.0"
  And campers.py contains dependency "fire>=0.7.0"
  And campers.py contains dependency "textual>=0.47.0"
  When I run "uv run -m campers --help"
  Then exit code is 0
  And no installation errors occur

@smoke
Scenario: Fire CLI routing
  Given campers.py exists in project root
  And campers.py defines Moondock class
  When I run "uv run -m campers --help"
  Then Fire routes to CLI commands
  And output contains "campers"
