Feature: Mutagen File Synchronization

@error @dry_run
Scenario: Mutagen not installed with sync_paths configured
  Given CAMPERS_TEST_MODE is "0"
  And config file with defaults section
  And defaults have sync_paths configured
  And mutagen is not installed locally
  When I run campers command "run -c 'echo test'"
  Then command fails with RuntimeError
  And error message contains "Mutagen is not installed locally"
  And error message contains "https://github.com/mutagen-io/mutagen"

@smoke @dry_run
Scenario: No sync_paths skips mutagen operations
  Given config file with defaults section
  And defaults have no sync_paths
  When I run campers command "run -c 'echo test'"
  Then mutagen installation check is skipped
  And mutagen session is not created
  And command executes from home directory

@smoke @localstack @pilot
Scenario: Create mutagen sync session
  Given config file with defaults section
  And LocalStack is healthy and responding
  And defaults have sync_paths with local "~/myproject" and remote "~/myproject"
  When I run campers command "run -c 'echo test'"
  Then mutagen session is created with name pattern "campers-"
  And sync mode is "two-way-resolved"
  And sync local path is "~/myproject"
  And sync remote path is "ubuntu@{host}:~/myproject"

@smoke @localstack @pilot
Scenario: Wait for initial sync completion
  Given config file with defaults section
  And LocalStack is healthy and responding
  And defaults have sync_paths configured
  When I run campers command "run -c 'echo test'"
  Then command exit code is 0

@error @localstack @pilot
Scenario: Initial sync timeout
  Given config file with defaults section
  And LocalStack is healthy and responding
  And defaults have sync_paths configured
  And sync does not complete within timeout
  When I run campers command "run -c 'echo test'"
  Then command fails with RuntimeError
  And error message contains "Mutagen sync timed out"
  And mutagen session is terminated
  And instance remains running

@smoke @localstack @pilot
Scenario: Execute startup_script after sync completes
  Given config file with defaults section
  And LocalStack is healthy and responding
  And defaults have startup_script "echo 'Startup script executed successfully'"
  And defaults have sync_paths with local "~/myproject" and remote "~/myproject"
  When I run campers command "run -c 'echo test'"
  Then command exit code is 0
  And status message "Running startup_script..." is logged
  And status message "Startup script completed successfully" is logged

@error @dry_run
Scenario: startup_script without sync_paths raises error
  Given config file with defaults section
  And defaults have startup_script "echo test"
  And defaults have no sync_paths
  When I run campers command "run"
  Then command fails with ValueError
  And error message contains "startup_script is defined but no sync_paths configured"

@smoke @localstack @pilot
Scenario: Command executes from synced directory
  Given config file with defaults section
  And LocalStack is healthy and responding
  And defaults have sync_paths with local "~/myproject" and remote "~/myproject"
  And mutagen sync completes
  When I run campers command "run -c 'pwd'"
  Then working directory is sync remote path
  And command exit code is 0

@smoke @dry_run
Scenario: Ignore patterns excluded from sync
  Given config file with defaults section
  And defaults have ignore patterns ["*.pyc", "__pycache__", "*.log"]
  And defaults have sync_paths configured
  When mutagen sync session is created
  Then ignore pattern "*.pyc" is configured
  And ignore pattern "__pycache__" is configured
  And ignore pattern "*.log" is configured

@smoke @dry_run
Scenario: VCS files excluded by default
  Given config file with defaults section
  And defaults have sync_paths configured
  And defaults have include_vcs false
  When mutagen sync session is created
  Then ignore pattern ".git" is configured
  And ignore pattern ".gitignore" is configured

@smoke @dry_run
Scenario: VCS files included when enabled
  Given config file with defaults section
  And defaults have sync_paths configured
  And defaults have include_vcs true
  When mutagen sync session is created
  Then ignore pattern ".git" is not configured
  And ignore pattern ".gitignore" is not configured

@integration @localstack @pilot
Scenario: Mutagen session cleanup on normal exit
  Given LocalStack is healthy and responding
  And mutagen sync session is running
  When command completes normally
  Then mutagen session is terminated
  And session is removed from mutagen list

@integration @localstack @pilot
Scenario: Mutagen session cleanup on error
  Given LocalStack is healthy and responding
  And mutagen sync session is running
  And startup_script is configured
  When startup_script fails with exit code 1
  Then command fails with RuntimeError
  And mutagen session is terminated
  And SSH connection is closed
  And instance remains running

@smoke @dry_run
Scenario: Test mode simulates mutagen sync
  Given CAMPERS_TEST_MODE is "1"
  And config file with defaults section
  And defaults have sync_paths configured
  And defaults have startup_script "echo test"
  When I run campers command "run -c 'echo done'"
  Then mutagen installation check is skipped
  And mutagen session creation is skipped
  And status message "Starting Mutagen file sync..." is logged
  And status message "Waiting for initial file sync to complete..." is logged
  And status message "File sync completed" is logged
  And status message "Running startup_script..." is logged
  And status message "Startup script completed successfully" is logged

@smoke @localstack @pilot
Scenario: Orphaned session cleanup before new session
  Given LocalStack is healthy and responding
  And orphaned mutagen session exists with name "campers-123"
  And config file with defaults section
  And defaults have sync_paths configured
  When I run campers command "run -c 'echo test'"
  Then orphaned session "campers-123" is terminated
  And new mutagen session is created
