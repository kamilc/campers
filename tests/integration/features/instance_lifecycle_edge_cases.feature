Feature: Instance Lifecycle Edge Cases and Error Handling

Background:
  Given LocalStack is healthy and responding

@error @localstack
Scenario: Stop instance in stopping state returns current state
  Given an instance in "stopping" state with name "campers-myproject-main"
  When I run "campers stop campers-myproject-main"
  Then the command returns instance details
  And the instance state is "stopping" or "stopped"

@error
Scenario: Start instance in pending state returns error
  Given an instance in "pending" state with name "campers-myproject-main"
  When I run "campers start campers-myproject-main"
  Then an error occurs with message "Instance is not in stopped state"

@error @localstack
Scenario: Terminate waiter timeout raises error
  Given a running instance with name "campers-myproject-main"
  And stop_instance will timeout after 10 minutes
  When I run "campers stop campers-myproject-main" with timeout override to 1 second
  Then an error occurs with message "timeout"
  And error message includes "timeout"

@smoke @localstack
Scenario: Volume size retrieval for stopped instance
  Given a stopped instance with name "campers-myproject-main"
  And the instance has 500GB root volume
  When volume size is retrieved
  Then volume size is 500

@smoke @localstack
Scenario: Volume size retrieval handles missing volume gracefully
  Given an instance with name "campers-myproject-main"
  And the instance has no root volume mapping
  When volume size is retrieved
  Then volume size is 0 or None returned

@error @localstack
Scenario: Instance operations fail with AWS permission errors
  Given AWS credentials lack EC2 permissions
  And an instance with name "campers-myproject-main" exists
  When I run "campers stop campers-myproject-main"
  Then an error occurs with message "Insufficient AWS permissions"

@smoke @localstack
Scenario: Stop instance by ID when multiple instances with same name
  Given multiple instances exist with same timestamp-based name
  And instance "i-12345" is running
  When I run "campers stop i-12345"
  Then instance "i-12345" is stopped
  And other instances are unaffected
