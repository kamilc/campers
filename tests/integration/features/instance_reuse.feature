Feature: Smart Instance Reuse

@smoke @mock
Scenario: First run creates new instance with git-based name
  Given I am in a git repository with project "myproject" on branch "main"
  And no instance with name "campers-myproject-main" exists
  When I run "campers run test-camp"
  Then an instance is created with name "campers-myproject-main"
  And the instance is in "running" state
  And the instance is not reused

@smoke @mock
Scenario: Second run reuses stopped instance
  Given I am in a git repository with project "myproject" on branch "main"
  And a stopped instance with name "campers-myproject-main" exists
  When I run "campers run test-camp"
  Then the existing instance is started
  And no new instance is created
  And the instance is reused

@smoke @mock
Scenario: Different branch creates different instance
  Given I am in a git repository with project "myproject" on branch "main"
  And a stopped instance with name "campers-myproject-main" exists
  And I switch to branch "feature/new-api"
  When I run "campers run test-camp"
  Then a new instance is created with name "campers-myproject-feature-new-api"
  And the instance "campers-myproject-main" remains stopped

@error @mock
Scenario: Running instance error prevents creation
  Given I am in a git repository with project "myproject" on branch "main"
  And a running instance with name "campers-myproject-main" exists
  When I run "campers run test-camp"
  Then an error occurs with message "Instance 'campers-myproject-main' is already running"
  And the error suggests stopping or destroying the instance
  And no new instance is created
