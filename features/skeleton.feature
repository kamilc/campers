Feature: Moondock CLI Execution

@smoke
Scenario: Execute CLI with help flag
  Given moondock.py exists in project root
  And moondock.py contains PEP 723 dependencies
  When I run "uv run -m moondock --help"
  Then exit code is 0
  And output contains "moondock"

@smoke
Scenario: Verify dependency installation
  Given moondock.py exists in project root
  And moondock.py contains dependency "boto3>=1.40.0"
  And moondock.py contains dependency "PyYAML>=6.0"
  And moondock.py contains dependency "fire>=0.7.0"
  And moondock.py contains dependency "textual>=0.47.0"
  When I run "uv run -m moondock --help"
  Then exit code is 0
  And no installation errors occur

@smoke
Scenario: Fire CLI routing
  Given moondock.py exists in project root
  And moondock.py defines Moondock class
  When I run "uv run -m moondock --help"
  Then Fire routes to CLI commands
  And output contains "moondock"
