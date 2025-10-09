Feature: User-Friendly Error Messages

@error
Scenario: Missing VPC error is user-friendly
  Given AWS credentials are configured
  And running in real AWS mode
  And region "us-east-1" has no default VPC
  When I run run
  Then exit code is not 0
  And stdout does not contain "Shutdown requested - beginning cleanup"

@error
Scenario: Debug flag shows stack trace
  Given AWS credentials are configured
  And running in real AWS mode
  And region "us-east-1" has no default VPC
  When I run with environment "MOONDOCK_DEBUG=1 moondock run"
  Then exit code is not 0
  And stderr contains "Traceback"

@error @dry_run @no_credentials
Scenario: Missing credentials error is user-friendly
  Given AWS credentials are not configured
  When I run run
  Then exit code is not 0
  And stderr contains "AWS credentials not found"
  And stderr contains "aws configure"
  And stderr contains "AWS_ACCESS_KEY_ID"
  And stderr does not contain "Traceback"
