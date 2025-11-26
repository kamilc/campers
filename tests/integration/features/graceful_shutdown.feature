Feature: Graceful Shutdown with Resource Cleanup

@smoke @localstack @pilot
Scenario: SIGINT triggers cleanup during command execution
  Given LocalStack is healthy and responding
  And config file with defaults section
  And instance is running with all resources active
  And command is executing
  When SIGINT signal is received
  Then cleanup log shows "Shutdown requested - beginning cleanup..."
  And port forwarding is stopped first
  And mutagen session is terminated second
  And SSH connection is closed third
  And EC2 instance is terminated fourth
  And cleanup log shows "Cleanup completed successfully"
  And exit code is 130

@smoke @localstack @pilot
Scenario: SIGTERM triggers cleanup with correct exit code
  Given LocalStack is healthy and responding
  And config file with defaults section
  And instance is running with all resources active
  When SIGTERM signal is received
  Then cleanup sequence executes
  And exit code is 143

@smoke @localstack @pilot
Scenario: Cleanup during instance launch only cleans created resources
  Given LocalStack is healthy and responding
  And config file with defaults section
  And instance launch is in progress
  And SSH is not yet connected
  When SIGINT signal is received
  Then EC2 instance is terminated
  And SSH cleanup is skipped
  And mutagen cleanup is skipped
  And port forwarding cleanup is skipped

@smoke @localstack @pilot
Scenario: Cleanup continues despite individual failures
  Given LocalStack is healthy and responding
  And config file with defaults section
  And instance is running with all resources active
  And mutagen termination will fail
  When SIGINT signal is received
  Then port forwarding stops successfully
  And mutagen termination fails with logged error
  And SSH connection closes successfully
  And EC2 instance terminates successfully
  And cleanup log shows "Cleanup completed with 1 errors"
  And exit code is 130

@smoke @localstack @pilot
Scenario: Duplicate cleanup is prevented
  Given LocalStack is healthy and responding
  And config file with defaults section
  And instance is running with all resources active
  And cleanup is already in progress
  When another SIGINT signal is received
  Then second cleanup attempt is skipped
  And no duplicate cleanup errors occur

@smoke @localstack @pilot
Scenario: Normal completion without interruption
  Given LocalStack is healthy and responding
  And config file with defaults section
  When campers run completes normally
  Then cleanup happens in finally block

@smoke @dry_run
Scenario: Test mode graceful shutdown works correctly
  Given CAMPERS_TEST_MODE is "1"
  And config file with defaults section
  When SIGINT signal is received during execution
  Then cleanup sequence executes on mock resources
  And no actual AWS operations occur
  And exit code is 130
