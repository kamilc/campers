Feature: EC2 Instance Launch

@smoke @dry_run
Scenario: Launch instance from camp config
  Given config file with camp "jupyter-lab" defined
  And camp "jupyter-lab" has instance_type "t3.medium"
  And camp "jupyter-lab" has disk_size 50
  And camp "jupyter-lab" has region "us-east-1"
  When I launch instance with camp "jupyter-lab"
  Then instance is created in region "us-east-1"
  And instance type is "t3.medium"
  And root disk size is 50
  And instance state is "running"

@smoke @dry_run
Scenario: Launch instance with CLI overrides
  Given config file with defaults section
  And defaults have instance_type "t3.medium"
  When I launch instance with options "--instance-type m5.xlarge --region us-west-2"
  Then instance is created in region "us-west-2"
  And instance type is "m5.xlarge"

@smoke @dry_run
Scenario: Instance tagged correctly
  Given config file with camp "jupyter-lab" defined
  When I launch instance with camp "jupyter-lab"
  Then instance has tag "ManagedBy" with value "campers"
  And instance has tag "MachineConfig" with value "jupyter-lab"
  And instance has tag "Name" starting with "campers-"

@smoke @dry_run
Scenario: Ad-hoc instance tagged without camp name
  Given config file with defaults section
  When I launch instance with options "--instance-type t3.medium"
  Then instance has tag "MachineConfig" with value "ad-hoc"

@poc @localstack @pilot @timeout_330
Scenario: Launch and terminate instance via TUI with LocalStack
  Given a config file with camp "test-camp" defined
  And camp "test-camp" has instance_type "t3.micro"
  And camp "test-camp" has region "us-east-1"
  And camp "test-camp" has command "echo 'test'"
  And camp "test-camp" has on_exit "terminate"
  And LocalStack is healthy and responding

  When I launch the Campers TUI with the config file
  And I simulate running the "test-camp" in the TUI

  Then the TUI status widget shows "Status: terminating" within 180 seconds
  And the TUI log panel contains "Command completed successfully"
  And the TUI log panel contains "Cleanup completed successfully"
  And an EC2 instance was created in LocalStack with tag "MachineConfig" equal to "test-camp"
  And that instance has tag "ManagedBy" equal to "campers"
  And that instance is in "terminated" state
