Feature: Smart Instance Reuse

@smoke @localstack
Scenario: First run creates new instance with git-based name
  Given I am in a git repository with project "myproject" on branch "main"
  And no instance with name "moondock-myproject-main" exists
  When I run "moondock run test-machine"
  Then an instance is created with name "moondock-myproject-main"
  And the instance is in "running" state
  And the instance is not reused

@smoke @localstack
Scenario: Second run reuses stopped instance
  Given I am in a git repository with project "myproject" on branch "main"
  And a stopped instance with name "moondock-myproject-main" exists
  When I run "moondock run test-machine"
  Then the existing instance is started
  And no new instance is created
  And the instance is reused

@smoke @localstack
Scenario: Different branch creates different instance
  Given I am in a git repository with project "myproject" on branch "main"
  And a stopped instance with name "moondock-myproject-main" exists
  And I switch to branch "feature/new-api"
  When I run "moondock run test-machine"
  Then a new instance is created with name "moondock-myproject-feature-new-api"
  And the instance "moondock-myproject-main" remains stopped

@error @localstack
Scenario: Running instance error prevents creation
  Given I am in a git repository with project "myproject" on branch "main"
  And a running instance with name "moondock-myproject-main" exists
  When I run "moondock run test-machine"
  Then an error occurs with message "Instance 'moondock-myproject-main' is already running"
  And the error suggests stopping or destroying the instance
  And no new instance is created
