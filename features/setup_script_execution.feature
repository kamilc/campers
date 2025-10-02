Feature: Setup Script Execution

@smoke @dry_run
Scenario: Execute setup_script before command
  Given config file with machine "dev-box" defined
  And machine "dev-box" has setup_script "sudo apt update && sudo apt install -y python3-pip"
  When I run moondock command "run dev-box -c 'pip3 --version'"
  Then instance is launched
  And SSH connection is established
  And setup_script executes before command
  And setup_script exit code is 0
  And output is streamed to terminal
  And command "pip3 --version" executes on remote instance

@smoke @dry_run
Scenario: Multi-line setup_script execution
  Given config file with machine "dev-box" defined
  And machine "dev-box" has multi-line setup_script with shell features
  When I run moondock command "run dev-box -c 'uv --version'"
  Then setup_script executes successfully
  And setup_script exit code is 0
  And command executes after setup

@error @dry_run
Scenario: Setup_script failure prevents command execution
  Given config file with defaults section
  And defaults have setup_script "exit 1"
  When I run moondock command "run -c 'echo hello'"
  Then instance is launched
  And setup_script exit code is 1
  And command fails with RuntimeError
  And error message contains "Setup script failed with exit code: 1"
  And command "echo hello" does not execute

@smoke @dry_run
Scenario: Skip setup_script when not defined
  Given config file with machine "minimal-box" defined
  And machine "minimal-box" has no setup_script
  And machine "minimal-box" has command "hostname"
  When I run moondock command "run minimal-box"
  Then instance is launched
  And setup_script execution is skipped
  And command "hostname" executes on remote instance

@smoke @dry_run
Scenario: Setup_script executes from home directory
  Given config file with defaults section
  And defaults have setup_script "pwd"
  When I run moondock command "run -c 'echo done'"
  Then status message "Running setup_script..." is logged
  And status message "Setup script completed successfully" is logged

@integration @dry_run
Scenario: Machine config overrides defaults setup_script
  Given YAML defaults with setup_script "echo default setup"
  And machine "override-box" has setup_script "echo machine setup"
  When I run moondock command "run override-box -c 'echo done'"
  Then status message "Running setup_script..." is logged
  And status message "Setup script completed successfully" is logged

@smoke @dry_run
Scenario: Test mode simulates setup_script execution
  Given MOONDOCK_TEST_MODE is "1"
  And config file with defaults section
  And defaults have setup_script "sudo apt update"
  When I run moondock command "run -c 'python --version'"
  Then SSH connection is not actually attempted for setup_script
  And status message "Running setup_script..." is logged
  And status message "Setup script completed successfully" is logged

@integration @dry_run
Scenario: Launch instance without scripts or command
  Given config file with machine "bare-box" defined
  And machine "bare-box" has no setup_script
  And machine "bare-box" has no command
  When I run moondock command "run bare-box"
  Then instance is launched
  And SSH connection is not attempted
