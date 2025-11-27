Feature: SSH Command Execution

@smoke @localstack
Scenario: Execute command with campers run -c flag
  Given config file with defaults section
  And LocalStack is healthy and responding
  When I run campers command "run -c 'uptime'"
  Then instance is launched with SSH configured
  And SSH connection is established
  And command "uptime" executes on remote instance
  And command exit code is 0

@smoke @localstack
Scenario: Execute command from camp config
  Given config file with camp "test-box" defined
  And camp "test-box" has command "hostname"
  And LocalStack is healthy and responding
  When I run campers command "run test-box"
  Then SSH connection is established
  And command "hostname" executes on remote instance
  And output is streamed to terminal

@smoke @localstack
Scenario: Skip execution when no command specified
  Given config file with camp "test-box" defined
  And camp "test-box" has no command field
  And LocalStack is healthy and responding
  When I run campers command "run test-box"
  Then instance is launched
  And SSH connection is not attempted

@error @localstack
Scenario: Command fails with non-zero exit code
  Given config file with defaults section
  And LocalStack is healthy and responding
  When I run campers command "run -c 'exit 42'"
  Then SSH connection is established
  And command executes on remote instance
  And command exit code is 42

@error @dry_run
Scenario: Instance without public IP raises error
  Given config file with camp "private-box" defined
  And camp "private-box" has no public IP
  And camp "private-box" has command "echo test"
  When I run campers command "run private-box"
  Then command fails with ValueError
  And error message contains "does not have a public IP address"

@smoke @localstack @pilot @timeout_300
Scenario: Execute command via TUI with real SSH
  Given a config file with camp "test-box" defined
  And camp "test-box" has command "uptime"
  And camp "test-box" has instance_type "t3.micro"
  And camp "test-box" has region "us-east-1"
  And LocalStack is healthy and responding
  When I launch the Campers TUI with the config file
  And I simulate running the "test-box" in the TUI
  Then the TUI status widget shows "Status: terminating" within 180 seconds
  And the TUI log panel contains "Command completed successfully"
  And the TUI log panel contains "Cleanup completed successfully"

@smoke @localstack @pilot @timeout_300
Scenario: Execute command from camp config via TUI
  Given a config file with camp "test-box" defined
  And camp "test-box" has command "hostname"
  And LocalStack is healthy and responding
  When I launch the Campers TUI with the config file
  And I simulate running the "test-box" in the TUI
  Then the TUI log panel contains "Waiting for SSH to be ready"
  And the TUI log panel contains "SSH connection established"
  And the TUI log panel contains "Command completed successfully"

@smoke @localstack @pilot @timeout_300
Scenario: Skip SSH when no command specified via TUI
  Given a config file with camp "test-box" defined
  And camp "test-box" has no command field
  And LocalStack is healthy and responding
  When I launch the Campers TUI with the config file
  And I simulate running the "test-box" in the TUI
  Then the TUI log panel does not contain "Waiting for SSH to be ready"
  And the TUI log panel does not contain "Attempting SSH connection"
  And the TUI status widget shows "Status: terminating" within 180 seconds
  And the TUI log panel contains "Cleanup completed successfully"

@error @localstack @pilot @timeout_300
Scenario: Command fails with non-zero exit code via TUI
  Given a config file with camp "test-box" defined
  And camp "test-box" has command "exit 42"
  And LocalStack is healthy and responding
  When I launch the Campers TUI with the config file
  And I simulate running the "test-box" in the TUI
  Then the TUI log panel contains "Command completed with exit code: 42"
  And the TUI status widget shows "Status: terminating" within 180 seconds
  And the TUI log panel contains "Cleanup completed successfully"
