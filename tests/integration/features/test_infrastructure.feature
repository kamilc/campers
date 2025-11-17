Feature: Test Infrastructure Improvements

@smoke
Scenario: UUID prevents security group collisions
  Given multiple tests run in rapid succession
  When tests create security groups with UUID-based names
  Then no InvalidGroup.Duplicate errors occur
  And all security group names are unique

@smoke
Scenario: Cleanup errors are logged
  Given a scenario completes execution
  When after_scenario cleanup runs
  Then cleanup failures are logged with error level
  And expected errors are logged with debug level
  And test suite continues without crash

@smoke
Scenario: Test artifacts are cleaned
  Given test infrastructure improvements start
  When checking for pre-existing artifacts
  Then old key files in "$MOONDOCK_DIR/keys/" are removed
  And directory is empty or non-existent
