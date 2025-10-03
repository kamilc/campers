Feature: SSH Port Forwarding

@smoke @dry_run
Scenario: Create single SSH tunnel
  Given config file with ports [8888]
  When I run moondock command "run -c 'echo test'"
  Then SSH tunnel is created for port 8888
  And tunnel forwards localhost:8888 to remote:8888
  And status message "Creating SSH tunnel for port 8888..." is logged
  And status message "SSH tunnel established: localhost:8888 -> remote:8888" is logged

@smoke @dry_run
Scenario: Create multiple SSH tunnels
  Given config file with ports [8888, 6006, 5000]
  When I run moondock command "run -c 'echo test'"
  Then SSH tunnel is created for port 8888
  And SSH tunnel is created for port 6006
  And SSH tunnel is created for port 5000
  And status messages logged for all three ports

@smoke @dry_run
Scenario: Skip port forwarding when no ports configured
  Given config file with no ports specified
  When I run moondock command "run -c 'echo test'"
  Then no SSH tunnels are created
  And no port forwarding log messages appear

@smoke @dry_run
Scenario: Port forwarding after sync before startup_script
  Given config file with sync_paths configured
  And config file with ports [8888]
  And config file with startup_script "echo setup"
  When I run moondock command "run -c 'echo test'"
  Then status message "File sync completed" is logged before tunnels
  And status message "Creating SSH tunnel for port 8888..." is logged
  And status message "Running startup_script..." is logged after tunnels

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

