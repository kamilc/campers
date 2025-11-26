Feature: Setup Script Execution

@smoke @localstack
Scenario: Execute setup_script before command
  Given config file with camp "dev-box" defined
  And camp "dev-box" has setup_script "touch /tmp/setup_marker"
  And camp "dev-box" has command "test -f /tmp/setup_marker && echo success"
  And LocalStack is healthy and responding

  When I run campers command "run dev-box"

  Then instance is launched
  And SSH connection is established
  And status message "Running setup_script..." is logged
  And status message "Setup script completed successfully" is logged
  And marker file "/tmp/setup_marker" exists in SSH container
  And output contains "success"

@smoke @localstack
Scenario: Multi-line setup_script execution
  Given config file with camp "dev-box" defined
  And camp "dev-box" has multi-line setup_script
  And camp "dev-box" has command "cat /tmp/workspace/status.txt"
  And LocalStack is healthy and responding

  When I run campers command "run dev-box"

  Then setup_script executes successfully
  And setup_script exit code is 0
  And directory "/tmp/workspace" exists in SSH container
  And file "/tmp/workspace/status.txt" contains "Ready"
  And output contains "Ready"

@error @localstack
Scenario: Setup_script failure prevents command execution
  Given config file with defaults section
  And defaults have setup_script "exit 1"
  And LocalStack is healthy and responding

  When I run campers command "run -c 'echo hello'"

  Then instance is launched
  And setup_script exit code is 1
  And command fails with RuntimeError
  And error message contains "Setup script failed with exit code: 1"
  And command "echo hello" does not execute

@smoke @localstack
Scenario: Skip setup_script when not defined
  Given config file with camp "minimal-box" defined
  And camp "minimal-box" has no setup_script
  And camp "minimal-box" has command "hostname"
  And LocalStack is healthy and responding

  When I run campers command "run minimal-box"

  Then instance is launched
  And setup_script execution is skipped
  And command "hostname" executes on remote instance

@integration @localstack
Scenario: Machine config overrides defaults setup_script
  Given YAML defaults with setup_script "touch /tmp/default_marker"
  And camp "override-box" has setup_script "touch /tmp/camp_marker"
  And LocalStack is healthy and responding

  When I run campers command "run override-box -c 'ls /tmp'"

  Then marker file "/tmp/camp_marker" exists in SSH container
  And status message "Setup script completed successfully" is logged

@smoke @localstack @pilot @timeout_300
Scenario: Execute setup_script before command via TUI
  Given a config file with camp "dev-box" defined
  And camp "dev-box" has setup_script "touch /tmp/setup_marker"
  And camp "dev-box" has command "test -f /tmp/setup_marker && echo success"
  And LocalStack is healthy and responding

  When I launch the Moondock TUI with the config file
  And I simulate running the "dev-box" in the TUI

  Then the TUI log panel contains "Running setup_script..."
  And the TUI log panel contains "Setup script completed successfully"
  And the TUI log panel contains "Command completed successfully"
  And marker file "/tmp/setup_marker" exists in SSH container
  And the TUI status widget shows "Status: terminating" within 180 seconds

@smoke @localstack @pilot @timeout_300
Scenario: Multi-line setup_script via TUI
  Given a config file with camp "dev-box" defined
  And camp "dev-box" has multi-line setup_script
  And camp "dev-box" has command "cat /tmp/workspace/status.txt"
  And LocalStack is healthy and responding

  When I launch the Moondock TUI with the config file
  And I simulate running the "dev-box" in the TUI

  Then the TUI log panel contains "Setup script completed successfully"
  And directory "/tmp/workspace" exists in SSH container
  And file "/tmp/workspace/status.txt" contains "Ready"
  And the TUI status widget shows "Status: terminating" within 180 seconds

@error @localstack @pilot @timeout_300
Scenario: Setup_script failure shown in TUI
  Given a config file with camp "test-box" defined
  And camp "test-box" has setup_script "exit 1"
  And camp "test-box" has command "echo hello"
  And LocalStack is healthy and responding

  When I launch the Moondock TUI with the config file
  And I simulate running the "test-box" in the TUI

  Then the TUI log panel contains "Running setup_script..."
  And the TUI log panel contains "Setup script failed with exit code: 1"
  And the TUI log panel does not contain "Command completed"
  And the TUI status widget shows "Status: error" within 180 seconds

@smoke @localstack @pilot @timeout_300
Scenario: Skip setup_script via TUI when not defined
  Given a config file with camp "minimal-box" defined
  And camp "minimal-box" has no setup_script
  And camp "minimal-box" has command "hostname"
  And LocalStack is healthy and responding

  When I launch the Moondock TUI with the config file
  And I simulate running the "minimal-box" in the TUI

  Then the TUI log panel does not contain "Running setup_script..."
  And the TUI log panel contains "Command completed successfully"
  And the TUI status widget shows "Status: terminating" within 180 seconds

@integration @localstack @pilot @timeout_300
Scenario: Machine config overrides defaults via TUI
  Given a config file with defaults section
  And defaults have setup_script "touch /tmp/default_marker"
  And camp "override-box" has setup_script "touch /tmp/camp_marker"
  And camp "override-box" has command "ls /tmp"
  And LocalStack is healthy and responding

  When I launch the Moondock TUI with the config file
  And I simulate running the "override-box" in the TUI

  Then the TUI log panel contains "Setup script completed successfully"
  And marker file "/tmp/camp_marker" exists in SSH container
  And the TUI status widget shows "Status: terminating" within 180 seconds

@smoke @dry_run
Scenario: Setup_script executes from home directory
  Given config file with defaults section
  And defaults have setup_script "pwd"
  When I run campers command "run -c 'echo done'"
  Then status message "Running setup_script..." is logged
  And status message "Setup script completed successfully" is logged

@smoke @dry_run
Scenario: Test mode simulates setup_script execution
  Given CAMPERS_TEST_MODE is "1"
  And config file with defaults section
  And defaults have setup_script "sudo apt update"
  When I run campers command "run -c 'python --version'"
  Then SSH connection is not actually attempted for setup_script
  And status message "Running setup_script..." is logged
  And status message "Setup script completed successfully" is logged

@integration @dry_run
Scenario: Launch instance without scripts or command
  Given config file with camp "bare-box" defined
  And camp "bare-box" has no setup_script
  And camp "bare-box" has no command
  When I run campers command "run bare-box"
  Then instance is launched
  And SSH connection is not attempted
