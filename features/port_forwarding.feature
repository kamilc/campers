Feature: SSH Port Forwarding

@smoke @localstack
Scenario: Create single SSH tunnel
  Given config file with ports [8888]
  And LocalStack is healthy and responding
  And HTTP server runs on port 8888 in SSH container

  When I run moondock command "run -c 'sleep 30'"

  Then SSH tunnel is created for port 8888
  And tunnel forwards localhost:8888 to remote:8888
  And HTTP request to localhost:8888 succeeds

@smoke @localstack
Scenario: Create multiple SSH tunnels
  Given config file with ports [8888, 8889, 8890]
  And LocalStack is healthy and responding
  And HTTP server runs on port 8888 in SSH container
  And HTTP server runs on port 8889 in SSH container
  And HTTP server runs on port 8890 in SSH container

  When I run moondock command "run -c 'sleep 30'"

  Then status messages logged for all three ports
  And HTTP request to localhost:8888 succeeds
  And HTTP request to localhost:8889 succeeds
  And HTTP request to localhost:8890 succeeds

@smoke @localstack
Scenario: Skip port forwarding when no ports configured
  Given config file with no ports specified
  And LocalStack is healthy and responding

  When I run moondock command "run -c 'echo test'"

  Then no SSH tunnels are created
  And no port forwarding log messages appear

@smoke @localstack @pilot
Scenario: Create single SSH tunnel via TUI
  Given a config file with machine "test-box" defined
  And machine "test-box" has command "sleep 30"
  And machine "test-box" has ports [8888]
  And LocalStack is healthy and responding
  And HTTP server runs on port 8888 in SSH container

  When I launch the Moondock TUI with the config file
  And I simulate running the "test-box" in the TUI

  Then the TUI log panel contains "Creating SSH tunnel for port 8888..."
  And the TUI log panel contains "SSH tunnel established: localhost:8888 -> remote:8888"
  And HTTP request to localhost:8888 succeeds

@smoke @localstack @pilot
Scenario: Create multiple SSH tunnels via TUI
  Given a config file with machine "test-box" defined
  And machine "test-box" has command "sleep 30"
  And machine "test-box" has ports [8888, 8889, 8890]
  And LocalStack is healthy and responding
  And HTTP server runs on port 8888 in SSH container
  And HTTP server runs on port 8889 in SSH container
  And HTTP server runs on port 8890 in SSH container

  When I launch the Moondock TUI with the config file
  And I simulate running the "test-box" in the TUI

  Then the TUI log panel contains "Creating SSH tunnel for port 8888..."
  And the TUI log panel contains "Creating SSH tunnel for port 8889..."
  And the TUI log panel contains "Creating SSH tunnel for port 8890..."
  And HTTP request to localhost:8888 succeeds
  And HTTP request to localhost:8889 succeeds
  And HTTP request to localhost:8890 succeeds

@smoke @localstack @pilot
Scenario: Skip port forwarding when no ports configured via TUI
  Given a config file with machine "test-box" defined
  And machine "test-box" has command "sleep 10"
  And machine "test-box" has no ports specified
  And LocalStack is healthy and responding

  When I launch the Moondock TUI with the config file
  And I simulate running the "test-box" in the TUI

  Then the TUI log panel does not contain "Creating SSH tunnel"

@smoke @localstack @pilot
Scenario: Port forwarding lifecycle via TUI
  Given a config file with machine "test-box" defined
  And machine "test-box" has command "sleep 10"
  And machine "test-box" has ports [8888]
  And LocalStack is healthy and responding
  And HTTP server runs on port 8888 in SSH container

  When I launch the Moondock TUI with the config file
  And I simulate running the "test-box" in the TUI

  Then the TUI log panel contains "Creating SSH tunnel for port 8888..."
  And the TUI log panel contains "SSH tunnel established: localhost:8888 -> remote:8888"

@smoke @dry_run
Scenario: Test mode simulates SSH tunnels
  Given MOONDOCK_TEST_MODE is "1"
  And config file with ports [8888, 6006]
  When I run moondock command "run -c 'echo test'"
  Then SSH tunnel creation is skipped
  And status message "Creating SSH tunnel for port 8888..." is logged
  And status message "SSH tunnel established: localhost:8888 -> remote:8888" is logged
  And status message "Creating SSH tunnel for port 6006..." is logged
  And status message "SSH tunnel established: localhost:6006 -> remote:6006" is logged

@smoke @dry_run
Scenario: Localhost-only binding for security
  Given config file with ports [8888]
  When I run moondock command "run -c 'echo test'"
  Then status message "Creating SSH tunnel for port 8888..." is logged
  And status message "SSH tunnel established: localhost:8888 -> remote:8888" is logged

