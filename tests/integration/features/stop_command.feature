Feature: Stop Command

@smoke @dry_run
Scenario: Stop instance by EC2 instance ID
  Given running instance "i-0123abcd" with MachineConfig "dev-workstation"
  When I run stop command with "i-0123abcd"
  Then instance "i-0123abcd" is terminated
  And success message is printed to stdout
  And command exits with status 0

@smoke @dry_run
Scenario: Stop instance by MachineConfig name
  Given running instance "i-abc123" with MachineConfig "dev-workstation"
  When I run stop command with "dev-workstation"
  Then instance "i-abc123" is terminated
  And success message is printed to stdout
  And command exits with status 0

@error @dry_run
Scenario: No matching instance found
  Given no campers instances exist
  When I run stop command with "non-existent"
  Then command fails with exit code 1
  And error message contains "No campers-managed instances matched"
  And error is printed to stderr

@error @dry_run
Scenario: Ambiguous MachineConfig name
  Given running instance "i-first" with MachineConfig "dev-workstation"
  And running instance "i-second" with MachineConfig "dev-workstation"
  When I run stop command with "dev-workstation"
  Then command fails with exit code 1
  And error message contains "Ambiguous camp config"
  And disambiguation help lists instance IDs "i-first" and "i-second"
  And error is printed to stderr

@error @dry_run
Scenario: Stop instance in stopping state
  Given instance "i-stopping" in state "stopping" with MachineConfig "test-camp"
  When I run stop command with "i-stopping"
  Then command fails with exit code 1
  And error is printed to stderr

@error @dry_run
Scenario: Already terminated instance not found
  Given instance "i-terminated" in state "terminated"
  When I run stop command with "i-terminated"
  Then command fails with exit code 1
  And error message contains "No campers-managed instances matched"

@error @dry_run
Scenario: Insufficient AWS permissions
  Given user has AWS credentials with no EC2 permissions
  When I run stop command with "some-instance"
  Then command fails with exit code 1
  And error message contains "Insufficient AWS permissions"
  And error is printed to stderr

@error @dry_run
Scenario: Termination timeout
  Given running instance "i-timeout" with MachineConfig "test-camp"
  And terminate_instance raises RuntimeError
  When I run stop command with "i-timeout"
  Then command fails with exit code 1
  And error is printed to stderr

@smoke @dry_run
Scenario: Stop instance with region argument
  Given running instance "i-region123" with MachineConfig "test-camp"
  When I run stop command with name or id "i-region123" and region "us-east-1"
  Then instance "i-region123" is terminated
  And command exits with status 0

@error @dry_run
Scenario: No matching instance does not call terminate
  Given no campers instances exist
  When I run stop command with "non-existent"
  Then terminate_instance was not called
  And command fails with exit code 1

@error @dry_run
Scenario: Ambiguous name does not call terminate
  Given running instance "i-first" with MachineConfig "dev-workstation"
  And running instance "i-second" with MachineConfig "dev-workstation"
  When I run stop command with "dev-workstation"
  Then terminate_instance was not called
  And command fails with exit code 1

@error @dry_run
Scenario: Instance not found during termination
  Given running instance "i-found" with MachineConfig "test-camp"
  And terminate_instance raises ClientError "InvalidInstanceID.NotFound"
  When I run stop command with "i-found"
  Then command fails with exit code 1
  And error message contains "AWS API error"
  And error is printed to stderr

@error @dry_run
Scenario: Permission denied during termination
  Given running instance "i-denied" with MachineConfig "test-camp"
  And terminate_instance raises ClientError "UnauthorizedOperation"
  When I run stop command with "i-denied"
  Then command fails with exit code 1
  And error message contains "Insufficient AWS permissions"
  And error is printed to stderr
