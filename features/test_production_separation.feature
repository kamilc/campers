Feature: Test-Production Code Separation

  Background:
    Given the moondock codebase has been refactored

  @smoke
  Scenario: Production code contains no test contamination
    When I search for test-specific environment variables in production code
    Then I find zero matches for "MOONDOCK_TEST_MODE" in moondock/
    And I find zero matches for "SSH_PORT_" in moondock/ssh.py
    And I find zero matches for "AWS_ENDPOINT_URL" detection in moondock/ec2.py
    And I find zero matches for "_run_test_mode" in moondock/__main__.py
    And I find zero matches for "SSH_KEY_FILE_" in moondock/
    And I find zero matches for "MOONDOCK_TARGET_INSTANCE_IDS" in moondock/
    And I find zero matches for "SSH_READY_" in moondock/
    And I find zero matches for "HTTP_SERVERS_READY_" in moondock/
    And I find zero matches for "MONITOR_ERROR_" in moondock/
    And I find zero matches for "MOONDOCK_SSH_CONTAINER_BOOT_TIMEOUT" in moondock/
    And I find zero matches for "MOONDOCK_SSH_DELAY_SECONDS" in moondock/
    And I find zero matches for "MOONDOCK_NO_PUBLIC_IP" in moondock/
    And I find zero matches for "MOONDOCK_SYNC_TIMEOUT" in moondock/

  @smoke
  Scenario: SSH connection logic is simplified
    When I examine the get_ssh_connection_details function in moondock/ssh.py
    Then the function is less than 10 lines of code
    And the function contains no LocalStack logic
    And the function contains no Docker container logic

  @smoke
  Scenario: Test fakes are isolated from production code
    When I search for imports of test fakes in production code
    Then I find zero imports of "FakeEC2Manager" in moondock/
    And I find zero imports of "FakeSSHManager" in moondock/
    And I find zero imports of "tests.fakes" in moondock/
    And all test infrastructure code is in tests/ or features/ directories

  @smoke
  Scenario: is_localstack_environment function is removed
    When I search for LocalStack detection in moondock/ec2.py
    Then I find zero matches for "is_localstack_environment"
    And I find zero matches for "localstack" in moondock/ec2.py

  Scenario: Production CLI behavior unchanged
    When I verify CLI does not contain test-specific arguments
    Then no new test-mode command-line arguments are added
    And SSH connection functions are properly defined
