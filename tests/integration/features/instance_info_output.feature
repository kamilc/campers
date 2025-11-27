Feature: Instance Info Output

@smoke @dry_run
Scenario: Info command displays launch time
  Given I have a running instance with camp "test-box"
  When I run campers command "info test-box"
  Then output contains launch time information
  And output contains ISO timestamp
  And timestamp is recent

@smoke @dry_run
Scenario: Info command displays unique_id
  Given I have a running instance with camp "test-box"
  When I run campers command "info test-box"
  Then output contains unique identifier
  And unique ID matches instance tag

@smoke @dry_run
Scenario: Info command displays key_file path
  Given I have a running instance with camp "test-box"
  When I run campers command "info test-box"
  Then output contains key file path
  And key file path matches expected format

@smoke @dry_run
Scenario: Uptime calculates correctly from launch_time
  Given I have a running instance launched 30 minutes ago
  When I run campers command "info test-instance"
  Then output contains uptime information
  And uptime is approximately 30 minutes
