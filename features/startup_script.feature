Feature: Startup Script Execution

@smoke @dry_run
Scenario: Execute startup_script after Mutagen sync
  Given config file with defaults section
  And defaults have sync_paths with local "~/myproject" and remote "~/myproject"
  And defaults have startup_script "source .venv/bin/activate"
  When I run moondock command "run -c 'python --version'"
  Then status message "Running startup_script..." is logged
  And status message "Startup script completed successfully" is logged
  And startup_script exit code is 0

@smoke @dry_run
Scenario: Multi-line startup_script with shell features
  Given config file with defaults section
  And defaults have sync_paths configured
  And defaults have multi-line startup_script with shell features
  When I run moondock command "run -c 'pwd'"
  Then startup_script exit code is 0
  And status message "Startup script completed successfully" is logged

@error @dry_run
Scenario: Startup_script failure prevents command execution
  Given config file with defaults section
  And defaults have sync_paths configured
  And defaults have startup_script "exit 42"
  When I run moondock command "run -c 'echo hello'"
  Then command fails with RuntimeError
  And error message contains "Startup script failed with exit code: 42"
  And instance remains running

@smoke @dry_run
Scenario: Skip startup_script when not defined
  Given config file with defaults section
  And defaults have sync_paths configured
  And defaults have no startup_script
  When I run moondock command "run -c 'hostname'"
  Then startup_script execution is skipped
  And command exit code is 0

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

@integration @dry_run
Scenario: Configuration hierarchy for startup_script
  Given YAML defaults with startup_script "echo default"
  And machine "override-box" has startup_script "echo machine"
  And machine "override-box" has sync_paths configured
  When I run moondock command "run override-box -c 'echo done'"
  Then status message "Running startup_script..." is logged
  And status message "Startup script completed successfully" is logged

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
