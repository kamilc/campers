Feature: EC2 SSH Key Management

@smoke @dry_run
Scenario: SSH key created before instance launch
  Given valid configuration
  When I launch instance
  Then key pair is created in AWS
  And key pair name starts with "moondock-"
  And private key is saved to "~/.moondock/keys/{unique_id}.pem"
  And key file permissions are 0600

@smoke @dry_run
Scenario: Key pair used during instance launch
  Given valid configuration
  When I launch instance
  Then instance is launched with key pair name
  And key name matches security group unique_id

@error @dry_run
Scenario: Rollback deletes key pair on launch failure
  Given key pair is created
  When instance launch fails
  Then key pair is deleted from AWS
  And key file is deleted from disk
