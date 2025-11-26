Feature: Instance Naming and Detection

@smoke @localstack
Scenario: Git-based instance naming with project and branch
  Given I am in a git repository with project "myproject" on branch "main"
  When I create an instance with git context
  Then the instance name is "campers-myproject-main"

@smoke @localstack
Scenario: Sanitization converts special characters to dashes
  Given I am in a git repository with project "myproject" on branch "feature/new-api@v2"
  When I create an instance with git context
  Then the instance name is "campers-myproject-feature-new-api-v2"

@smoke @localstack
Scenario: Timestamp naming when not in git repository
  Given I am not in a git repository
  When I create an instance with fallback naming
  Then the instance name matches pattern "campers-[0-9]{10}"

@smoke @localstack
Scenario: Timestamp naming when git command times out
  Given git commands timeout after 2 seconds
  When I create an instance with fallback naming
  Then the instance name matches pattern "campers-[0-9]{10}"
  And instance created successfully

@smoke @localstack
Scenario: Detached HEAD state uses timestamp naming
  Given I am in a git repository with detached HEAD state
  When I create an instance with fallback naming
  Then the instance name matches pattern "campers-[0-9]{10}"
