Feature: Exec Command for Lightweight Instance Access

@smoke @localstack
Scenario: Execute command via session file fast path
  Given a session file exists for camp "dev" with valid SSH info
  And a running instance exists for camp "dev"
  When I run campers exec "dev" with command "echo hello"
  Then the command should execute successfully
  And the exit code should be 0
  And exec output contains "hello"

@smoke @localstack
Scenario: Execute command via AWS discovery slow path
  Given no session file exists for camp "dev"
  And a running instance exists for camp "dev"
  When I run campers exec "dev" with command "echo hello"
  Then the command should execute successfully
  And the exit code should be 0

@smoke @localstack
Scenario: Execute command using instance ID
  Given a running instance "i-test123" exists for exec
  When I run campers exec "i-test123" with command "whoami"
  Then the command should execute successfully
  And the exit code should be 0

@error @localstack
Scenario: Error when no instance found
  When I run campers exec "nonexistent" with command "echo hello"
  Then the command should fail
  And exec error message includes "No running instance found"

@error @localstack
Scenario: Error when multiple instances match
  Given multiple running instances exist for camp "dev"
  When I run campers exec "dev" with command "echo hello"
  Then the command should fail
  And exec error message includes "Multiple instances found"

@error @localstack
Scenario: Error when instance is stopped
  Given a stopped instance exists for camp "dev"
  When I run campers exec "dev" with command "echo hello"
  Then the command should fail
  And error message indicates instance is not running

@smoke @localstack
Scenario: Command exit code propagation
  Given a running instance exists for camp "dev"
  When I run campers exec "dev" with command "exit 42"
  Then the exit code should be 42

@smoke @localstack
Scenario: Region flag narrows discovery scope
  Given running instances exist for camp "dev" in multiple regions
  When I run campers exec "dev" with command "echo hello" and region "us-east-1"
  Then the command should execute successfully on the us-east-1 instance
