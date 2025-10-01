Feature: EC2 Instance Launch

@smoke @dry_run @wip
Scenario: Launch instance from machine config
  Given config file with machine "jupyter-lab" defined
  And machine "jupyter-lab" has instance_type "t3.medium"
  And machine "jupyter-lab" has disk_size 50
  And machine "jupyter-lab" has region "us-east-1"
  When I launch instance with machine "jupyter-lab"
  Then instance is created in region "us-east-1"
  And instance type is "t3.medium"
  And root disk size is 50
  And instance state is "running"

@smoke @dry_run @wip
Scenario: Launch instance with CLI overrides
  Given config file with defaults section
  And defaults have instance_type "t3.medium"
  When I launch instance with options "--instance-type m5.xlarge --region us-west-2"
  Then instance is created in region "us-west-2"
  And instance type is "m5.xlarge"

@smoke @dry_run @wip
Scenario: Instance tagged correctly
  Given config file with machine "jupyter-lab" defined
  When I launch instance with machine "jupyter-lab"
  Then instance has tag "ManagedBy" with value "moondock"
  And instance has tag "MachineConfig" with value "jupyter-lab"
  And instance has tag "Name" starting with "moondock-"

@smoke @dry_run @wip
Scenario: Ad-hoc instance tagged without machine name
  Given config file with defaults section
  When I launch instance with options "--instance-type t3.medium"
  Then instance has tag "MachineConfig" with value "ad-hoc"
