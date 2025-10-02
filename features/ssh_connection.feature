Feature: SSH Connection Management

@integration @dry_run
Scenario: SSH connection retry with exponential backoff
  Given EC2 instance is starting up
  And SSH is not yet available
  When SSH connection is attempted
  Then connection retries with delays [1, 2, 4, 8, 16, 30]
  And connection succeeds when SSH is ready
  And total retry time is under 120 seconds

@error @dry_run
Scenario: SSH connection fails after all retries
  Given EC2 instance has no SSH access
  When SSH connection is attempted with 10 retries
  Then all connection attempts fail
  And error message is "Failed to establish SSH connection after 10 attempts"

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
