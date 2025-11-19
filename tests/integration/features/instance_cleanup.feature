Feature: Instance Cleanup Behavior (on_exit configuration)

@smoke @localstack
Scenario: Default on_exit=stop preserves instance and security group
  Given I have no on_exit configuration set
  And a running instance with all resources active
  When I send SIGINT (Ctrl+C) during execution
  Then the instance is stopped (not terminated)
  And the security group is preserved
  And the key pair is preserved
  And the key file exists in ~/.moondock/keys/
  And storage cost estimate is shown

@smoke @localstack
Scenario: on_exit=terminate destroys instance and all resources
  Given on_exit configuration is set to "terminate"
  And a running instance with all resources active
  When I send SIGINT (Ctrl+C) during execution
  Then the instance is terminated
  And the security group is deleted
  And the key pair is deleted
  And the key file is removed from filesystem

@smoke @localstack
Scenario: on_exit=stop preserves environment state for restart
  Given on_exit configuration is set to "stop"
  And a running instance with name "moondock-myproject-main"
  And I have created file "/tmp/test.txt" on the instance
  When I send SIGINT (Ctrl+C) during execution
  Then the instance is stopped
  And I run "moondock start moondock-myproject-main"
  And the file "/tmp/test.txt" still exists on the instance

@smoke @localstack
Scenario: Invalid on_exit value defaults to stop behavior
  Given on_exit configuration is set to "invalid-value"
  And a running instance with all resources active
  When I send SIGINT (Ctrl+C) during execution
  Then the instance is stopped (not terminated)
  And warning is logged about invalid on_exit value
