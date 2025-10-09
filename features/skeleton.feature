Feature: Moondock Skeleton Script Execution

@smoke
Scenario: Execute skeleton script with uv run
  Given moondock.py exists in project root
  And moondock.py contains PEP 723 dependencies
  When I run "uv run -m moondock hello"
  Then exit code is 0
  And output contains "moondock v0.1.0 - skeleton ready"

@smoke
Scenario: Verify dependency installation
  Given moondock.py exists in project root
  And moondock.py contains dependency "boto3>=1.40.0"
  And moondock.py contains dependency "PyYAML>=6.0"
  And moondock.py contains dependency "fire>=0.7.0"
  And moondock.py contains dependency "textual>=0.47.0"
  When I run "uv run -m moondock hello"
  Then exit code is 0
  And no installation errors occur

@smoke
Scenario: Fire CLI routing
  Given moondock.py exists in project root
  And moondock.py defines Moondock class
  And Moondock class has hello method
  When I run "uv run -m moondock hello"
  Then Fire routes to hello method
  And output contains "moondock v0.1.0 - skeleton ready"
