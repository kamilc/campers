Feature: EC2 Error Handling

@error @dry_run @no_credentials
Scenario: Missing AWS credentials
  Given no AWS credentials configured
  When I attempt to launch instance
  Then command fails with NoCredentialsError
  And error message contains "credentials"

@error @dry_run
Scenario: Invalid instance type
  Given config with instance_type "invalid.type"
  When I attempt to launch instance
  Then command fails with ClientError
  And error message contains "instance type"

@error @dry_run
Scenario: Instance launch timeout after 5 minutes
  Given instance fails to reach running state
  When 5 minutes elapse
  Then RuntimeError is raised with timeout message
  And rollback cleanup is attempted

@error @dry_run
Scenario: Resource name conflict handled
  Given key pair "campers-123" already exists
  And security group "campers-123" already exists
  When I launch instance with same unique_id
  Then existing key pair is deleted
  And existing security group is deleted
  And new resources are created
  And instance launches successfully

@error @dry_run
Scenario: Instance region mismatch with existing instance
  Given config file with defaults section
  And an existing instance for camp "web-server" in region "us-west-2"
  When I attempt to launch instance with camp "web-server" in region "us-east-1"
  Then command fails with RuntimeError
  And error message mentions existing region "us-west-2"
  And error message mentions configured region "us-east-1"
