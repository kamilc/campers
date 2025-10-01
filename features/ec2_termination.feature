Feature: EC2 Instance Termination

@smoke @dry_run
Scenario: Terminate instance and cleanup resources
  Given running instance with unique_id "1234567890"
  When I terminate the instance
  Then instance state is "terminated"
  And key pair "moondock-1234567890" is deleted from AWS
  And key file "~/.moondock/keys/1234567890.pem" is deleted
  And security group is deleted from AWS

@smoke @dry_run
Scenario: Instance termination waits for terminated state
  Given running instance
  When I terminate the instance
  Then termination waits for "terminated" state
  And security group cleanup happens after termination

@error @dry_run
Scenario: Termination timeout after 10 minutes
  Given instance fails to reach terminated state
  When 10 minutes elapse
  Then RuntimeError is raised with timeout message
