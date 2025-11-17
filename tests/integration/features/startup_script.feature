Feature: Startup Script Execution

@smoke @localstack
Scenario: Execute startup_script after Mutagen sync
  Given config file with defaults section
  And defaults have sync_paths configured
  And defaults have startup_script "touch ~/myproject/.startup_marker"
  And defaults have command "test -f ~/myproject/.startup_marker && echo success"
  And LocalStack is healthy and responding

  When I run moondock command "run -c 'test -f ~/myproject/.startup_marker && echo success'"

  Then instance is launched
  And SSH connection is established
  And status message "Running startup_script..." is logged
  And status message "Startup script completed successfully" is logged
  And startup_script creates file in synced directory
  And output contains "success"

@smoke @localstack
Scenario: Multi-line startup_script with shell features
  Given config file with defaults section
  And defaults have sync_paths configured
  And defaults have multi-line startup_script with shell features
  And defaults have command "cat /config/myproject/.venv/status.txt"
  And LocalStack is healthy and responding

  When I run moondock command "run -c 'cat /config/myproject/.venv/status.txt'"

  Then startup_script executes successfully
  And startup_script exit code is 0
  And startup_script creates file in synced directory
  And file "/config/myproject/.venv/status.txt" contains "Activated"
  And output contains "Activated"

@error @localstack
Scenario: Startup_script failure prevents command execution
  Given config file with defaults section
  And defaults have sync_paths configured
  And defaults have startup_script "exit 42"
  And LocalStack is healthy and responding

  When I run moondock command "run -c 'echo hello'"

  Then instance is launched
  And startup_script exit code is 42
  And command fails with RuntimeError
  And error message contains "Startup script failed with exit code: 42"
  And command "echo hello" does not execute
  And instance remains running

@smoke @localstack
Scenario: Skip startup_script when not defined
  Given config file with defaults section
  And defaults have sync_paths configured
  And defaults have no startup_script
  And defaults have command "hostname"
  And LocalStack is healthy and responding

  When I run moondock command "run -c 'hostname'"

  Then instance is launched
  And startup_script execution is skipped
  And command "hostname" executes on remote instance

@integration @localstack
Scenario: Configuration hierarchy for startup_script
  Given YAML defaults with startup_script "touch ~/myproject/.default_marker"
  And defaults have sync_paths configured
  And machine "override-box" has startup_script "touch ~/myproject/.machine_marker"
  And LocalStack is healthy and responding

  When I run moondock command "run override-box -c 'ls ~/myproject'"

  Then file "/config/myproject/.machine_marker" exists in SSH container
  And status message "Startup script completed successfully" is logged

@smoke @localstack @pilot @timeout_300
Scenario: Execute startup_script after sync via TUI
  Given a config file with defaults section
  And defaults have sync_paths configured
  And defaults have startup_script "touch ~/myproject/.startup_marker"
  And defaults have command "test -f ~/myproject/.startup_marker && echo success"
  And LocalStack is healthy and responding

  When I launch the Moondock TUI with the config file
  And I simulate running the machine in the TUI

  Then the TUI log panel contains "Running startup_script..."
  And the TUI log panel contains "Startup script completed successfully"
  And the TUI log panel contains "Command completed successfully"
  And file "/config/myproject/.startup_marker" exists in SSH container
  And the TUI status widget shows "Status: terminating" within 180 seconds

@smoke @localstack @pilot @timeout_300
Scenario: Multi-line startup_script via TUI
  Given a config file with defaults section
  And defaults have sync_paths configured
  And defaults have multi-line startup_script with shell features
  And defaults have command "cat ~/myproject/.venv/status.txt"
  And LocalStack is healthy and responding

  When I launch the Moondock TUI with the config file
  And I simulate running the machine in the TUI

  Then the TUI log panel contains "Startup script completed successfully"
  And file "/config/myproject/.venv/status.txt" contains "Activated"
  And the TUI status widget shows "Status: terminating" within 180 seconds

@error @localstack @pilot @timeout_300
Scenario: Startup_script failure shown in TUI
  Given a config file with defaults section
  And defaults have sync_paths configured
  And defaults have startup_script "exit 42"
  And defaults have command "echo hello"
  And LocalStack is healthy and responding

  When I launch the Moondock TUI with the config file
  And I simulate running the machine in the TUI

  Then the TUI log panel contains "Running startup_script..."
  And the TUI log panel contains "Startup script failed with exit code: 42"
  And the TUI log panel does not contain "Command completed"
  And the TUI status widget shows "Status: error" within 180 seconds

@smoke @localstack @pilot @timeout_300
Scenario: Skip startup_script via TUI when not defined
  Given a config file with defaults section
  And defaults have sync_paths configured
  And defaults have no startup_script
  And defaults have command "hostname"
  And LocalStack is healthy and responding

  When I launch the Moondock TUI with the config file
  And I simulate running the machine in the TUI

  Then the TUI log panel does not contain "Running startup_script..."
  And the TUI log panel contains "Command completed successfully"
  And the TUI status widget shows "Status: terminating" within 180 seconds

@integration @localstack @pilot @timeout_300
Scenario: Configuration hierarchy via TUI
  Given a config file with defaults section
  And defaults have sync_paths configured
  And defaults have startup_script "touch ~/myproject/.default_marker"
  And machine "override-box" has startup_script "touch ~/myproject/.machine_marker"
  And machine "override-box" has command "ls ~/myproject"
  And LocalStack is healthy and responding

  When I launch the Moondock TUI with the config file
  And I simulate running the "override-box" in the TUI

  Then the TUI log panel contains "Startup script completed successfully"
  And file "/config/myproject/.machine_marker" exists in SSH container
  And the TUI status widget shows "Status: terminating" within 180 seconds

@smoke @dry_run
Scenario: startup_script executes from synced directory
  Given config file with defaults section
  And defaults have sync_paths with local "~/myproject" and remote "~/myproject"
  And defaults have startup_script "pwd"
  When I run moondock command "run -c 'echo done'"
  Then startup_script exit code is 0
  And working directory is sync remote path

@smoke @dry_run
Scenario: Command executes from synced directory after startup_script
  Given config file with defaults section
  And defaults have sync_paths with local "~/app" and remote "~/app"
  And defaults have startup_script "source .venv/bin/activate"
  When I run moondock command "run -c 'pwd'"
  Then startup_script exit code is 0
  And command exit code is 0
  And working directory is sync remote path

@smoke @dry_run
Scenario: Test mode simulates startup_script execution
  Given MOONDOCK_TEST_MODE is "1"
  And config file with defaults section
  And defaults have sync_paths configured
  And defaults have startup_script "source .venv/bin/activate"
  When I run moondock command "run -c 'python --version'"
  Then SSH connection is not actually attempted for startup_script
  And status message "Running startup_script..." is logged
  And status message "Startup script completed successfully" is logged
