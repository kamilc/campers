Feature: Doctor Command

@smoke @dry_run
Scenario: Doctor reports missing VPC
  Given AWS credentials are configured
  And region "us-east-1" has no default VPC
  When I run doctor
  Then exit code is 0
  And stdout contains "No default VPC in us-east-1"
  And stdout contains "moondock setup"
  And stdout contains "aws ec2 create-default-vpc --region us-east-1"

@smoke @dry_run
Scenario: Doctor reports healthy infrastructure
  Given AWS credentials are configured
  And region "us-east-1" has default VPC
  And required IAM permissions exist
  When I run doctor
  Then exit code is 0
  And stdout contains "AWS credentials found"
  And stdout contains "Default VPC exists in us-east-1"
  And stdout contains "IAM permissions verified"

@dry_run
Scenario: Doctor is read-only
  Given AWS credentials are configured
  And region "us-east-1" has no default VPC
  When I run doctor
  Then exit code is 0
  And no AWS resources created
