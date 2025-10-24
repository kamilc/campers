Feature: SSH Connection Management

@integration @localstack
Scenario: SSH connection retry with exponential backoff
  Given config file with defaults section
  And LocalStack is healthy and responding
  And SSH container will delay startup by 10 seconds

  When I run moondock command "run -c 'echo ready'"

  Then SSH connection attempts are made
  And connection retry delays match [1, 2, 4, 8] seconds
  And connection succeeds when SSH becomes ready
  And command exit code is 0

@error @localstack
Scenario: SSH connection fails after all retries
  Given config file with defaults section
  And LocalStack is healthy and responding
  And SSH container is not accessible

  When I run moondock command "run -c 'echo test'"

  Then SSH connection is attempted multiple times
  And all connection attempts fail
  And error message contains "Failed to establish SSH connection"
  And command fails with non-zero exit code

@integration @localstack @pilot @timeout_300
Scenario: SSH connection retry progress shown in TUI
  Given a config file with machine "test-box" defined
  And machine "test-box" has command "echo ready"
  And machine "test-box" has instance_type "t3.micro"
  And machine "test-box" has region "us-east-1"
  And LocalStack is healthy and responding
  And SSH container will delay startup by 10 seconds

  When I launch the Moondock TUI with the config file
  And I simulate running the "test-box" in the TUI

  Then the TUI log panel contains "Attempting SSH connection (attempt 1/"
  And the TUI log panel contains "Attempting SSH connection (attempt 2/"
  And the TUI log panel contains "SSH connection established"
  And the TUI log panel contains "Command completed successfully"
  And the TUI status widget shows "Status: terminating" within 180 seconds

@error @localstack @pilot @timeout_300
Scenario: SSH connection failure shown in TUI
  Given a config file with machine "test-box" defined
  And machine "test-box" has command "echo test"
  And LocalStack is healthy and responding
  And SSH container is not accessible

  When I launch the Moondock TUI with the config file
  And I simulate running the "test-box" in the TUI

  Then the TUI log panel contains "Attempting SSH connection"
  And the TUI log panel contains "Failed to establish SSH connection"
  And the TUI status widget shows "Status: error" within 180 seconds

@integration @dry_run
Scenario: Shell features work correctly
  Given config file with defaults section
  When I run moondock command "run -c 'echo hello | grep ll'"
  Then SSH connection is established
  And command uses bash shell
  And output contains "hello"
  And command exit code is 0

@smoke @dry_run
Scenario: Commands execute in home directory
  Given config file with defaults section
  When I run moondock command "run -c 'pwd'"
  Then command output contains "/home/ubuntu"
  And command exit code is 0

@smoke @dry_run
Scenario: Test mode skips actual SSH connection
  Given MOONDOCK_TEST_MODE is "1"
  And config file with defaults section
  When I run moondock command "run -c 'hostname'"
  Then SSH connection is not actually attempted
  And status messages are printed
  And command_exit_code is 0 in result
