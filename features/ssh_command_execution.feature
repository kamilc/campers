Feature: SSH Command Execution

@smoke @dry_run
Scenario: Execute command with moondock run -c flag
  Given config file with defaults section
  When I run moondock command "run -c 'uptime'"
  Then instance is launched with SSH configured
  And SSH connection is established
  And command "uptime" executes on remote instance
  And command exit code is 0

@smoke @dry_run
Scenario: Execute command from machine config
  Given config file with machine "test-box" defined
  And machine "test-box" has command "hostname"
  When I run moondock command "run test-box"
  Then SSH connection is established
  And command "hostname" executes on remote instance
  And output is streamed to terminal

@smoke @dry_run
Scenario: Skip execution when no command specified
  Given config file with machine "test-box" defined
  And machine "test-box" has no command field
  When I run moondock command "run test-box"
  Then instance is launched
  And SSH connection is not attempted

@error @dry_run
Scenario: Command fails with non-zero exit code
  Given config file with defaults section
  When I run moondock command "run -c 'exit 42'"
  Then SSH connection is established
  And command executes on remote instance
  And command exit code is 42

@error @dry_run
Scenario: Instance without public IP raises error
  Given config file with machine "private-box" defined
  And machine "private-box" has no public IP
  And machine "private-box" has command "echo test"
  When I run moondock command "run private-box"
  Then command fails with ValueError
  And error message contains "does not have a public IP address"
