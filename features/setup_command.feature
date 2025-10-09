Feature: Setup Command

@smoke @dry_run
Scenario: Setup creates VPC when user confirms
  Given AWS credentials are configured
  And region "us-east-1" has no default VPC
  When I run setup with input "y"
  Then exit code is 0
  And stdout contains "Create default VPC now?"
  And stdout contains "Default VPC created in us-east-1"
  And stdout contains "Setup complete!"

@smoke @dry_run
Scenario: Setup confirms existing VPC
  Given AWS credentials are configured
  And region "us-east-1" has default VPC
  When I run setup
  Then exit code is 0
  And stdout contains "AWS credentials found"
  And stdout contains "Default VPC exists in us-east-1"
  And stdout contains "Setup complete!"

@dry_run
Scenario: Setup with custom region
  Given AWS credentials are configured
  When I run "moondock setup --region us-west-2"
  Then exit code is 0
  And stdout contains "Checking AWS prerequisites for us-west-2"

@dry_run
Scenario: Setup is idempotent
  Given AWS credentials are configured
  And region "us-east-1" has default VPC
  And "moondock setup" completed successfully
  When I run setup
  Then exit code is 0
  And VPC count in "us-east-1" is unchanged
