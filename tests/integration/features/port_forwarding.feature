Feature: SSH Port Forwarding

@smoke @localstack
Scenario: Create single SSH tunnel
  Given config file with ports [48888]
  And LocalStack is healthy and responding
  And HTTP server runs on port 48888 in SSH container

  When I run campers command "run -c 'sleep 30'"

  Then SSH tunnel is created for port 48888
  And tunnel forwards localhost:48888 to remote:48888
  And HTTP request to localhost:48888 succeeds

@smoke @localstack
Scenario: Create multiple SSH tunnels
  Given config file with ports [48888, 48889, 48890]
  And LocalStack is healthy and responding
  And HTTP server runs on port 48888 in SSH container
  And HTTP server runs on port 48889 in SSH container
  And HTTP server runs on port 48890 in SSH container

  When I run campers command "run -c 'sleep 30'"

  Then status messages logged for all three ports
  And HTTP request to localhost:48888 succeeds
  And HTTP request to localhost:48889 succeeds
  And HTTP request to localhost:48890 succeeds

@smoke @localstack
Scenario: Skip port forwarding when no ports configured
  Given config file with no ports specified
  And LocalStack is healthy and responding

  When I run campers command "run -c 'echo test'"

  Then no SSH tunnels are created
  And no port forwarding log messages appear

@smoke @localstack @pilot @timeout_300
Scenario: Create single SSH tunnel via TUI
  Given a config file with camp "test-box" defined
  And camp "test-box" has command "sleep 30"
  And camp "test-box" has ports [48888]
  And LocalStack is healthy and responding
  And HTTP server runs on port 48888 in SSH container

  When I launch the Campers TUI with the config file
  And I simulate running the "test-box" in the TUI

  Then the TUI log panel contains "Creating SSH tunnel for port 48888..."
  And the TUI log panel contains "SSH tunnel established: localhost:48888 -> remote:48888"
  And HTTP request to localhost:48888 succeeds

@smoke @localstack @pilot @timeout_300
Scenario: Create multiple SSH tunnels via TUI
  Given a config file with camp "test-box" defined
  And camp "test-box" has command "sleep 30"
  And camp "test-box" has ports [48888, 48889, 48890]
  And LocalStack is healthy and responding
  And HTTP server runs on port 48888 in SSH container
  And HTTP server runs on port 48889 in SSH container
  And HTTP server runs on port 48890 in SSH container

  When I launch the Campers TUI with the config file
  And I simulate running the "test-box" in the TUI

  Then the TUI log panel contains "Creating SSH tunnel for port 48888..."
  And the TUI log panel contains "Creating SSH tunnel for port 48889..."
  And the TUI log panel contains "Creating SSH tunnel for port 48890..."
  And HTTP request to localhost:48888 succeeds
  And HTTP request to localhost:48889 succeeds
  And HTTP request to localhost:48890 succeeds

@smoke @localstack @pilot @timeout_300
Scenario: Skip port forwarding when no ports configured via TUI
  Given a config file with camp "test-box" defined
  And camp "test-box" has command "sleep 10"
  And camp "test-box" has no ports specified
  And LocalStack is healthy and responding

  When I launch the Campers TUI with the config file
  And I simulate running the "test-box" in the TUI

  Then the TUI log panel does not contain "Creating SSH tunnel"

@smoke @localstack @pilot @timeout_300
Scenario: Port forwarding lifecycle via TUI
  Given a config file with camp "test-box" defined
  And camp "test-box" has command "sleep 10"
  And camp "test-box" has ports [48891]
  And LocalStack is healthy and responding
  And HTTP server runs on port 48891 in SSH container

  When I launch the Campers TUI with the config file
  And I simulate running the "test-box" in the TUI

  Then the TUI log panel contains "Creating SSH tunnel for port 48891..."
  And the TUI log panel contains "SSH tunnel established: localhost:48891 -> remote:48891"

@smoke @dry_run
Scenario: Test mode simulates SSH tunnels
  Given CAMPERS_TEST_MODE is "1"
  And config file with ports [48888, 6006]
  When I run campers command "run -c 'echo test'"
  Then SSH tunnel creation is skipped
  And status message "Creating SSH tunnel for port 48888..." is logged
  And status message "SSH tunnel established: localhost:48888 -> remote:48888" is logged
  And status message "Creating SSH tunnel for port 6006..." is logged
  And status message "SSH tunnel established: localhost:6006 -> remote:6006" is logged

@smoke @dry_run
Scenario: Localhost-only binding for security
  Given config file with ports [48888]
  When I run campers command "run -c 'echo test'"
  Then status message "Creating SSH tunnel for port 48888..." is logged
  And status message "SSH tunnel established: localhost:48888 -> remote:48888" is logged

