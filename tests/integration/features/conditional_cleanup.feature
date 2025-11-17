Feature: Conditional Cleanup Messages

Scenario: No cleanup message when no resources exist
  Given AWS credentials are configured
  And running in real AWS mode
  And region "us-east-1" has no default VPC
  When I run run
  Then exit code is not 0
  And stdout does not contain "Shutdown requested - beginning cleanup"

@dry_run
Scenario: Cleanup message shown when resources exist
  Given AWS credentials are configured
  And region "us-east-1" has default VPC
  And EC2 instance was created
  When user interrupts with Ctrl+C
  Then stdout contains "Shutdown requested - beginning cleanup"
