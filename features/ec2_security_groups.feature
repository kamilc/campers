Feature: EC2 Security Group Management

@smoke @dry_run @wip
Scenario: Security group created before instance launch
  Given valid configuration
  When I launch instance
  Then security group is created in default VPC
  And security group name starts with "moondock-"
  And security group has tag "ManagedBy" with value "moondock"

@smoke @dry_run @wip
Scenario: Security group allows SSH access
  Given valid configuration
  When I launch instance
  Then security group allows inbound TCP port 22 from "0.0.0.0/0"
  And security group allows all outbound traffic

@smoke @dry_run @wip
Scenario: Security group passed to instance at launch
  Given valid configuration
  When I launch instance
  Then instance is launched with security group ID
  And security group ID matches created group

@error @dry_run @wip
Scenario: Rollback deletes security group on launch failure
  Given security group is created
  When instance launch fails
  Then security group is deleted from AWS
