Feature: TUI Status Panel and Layout

@smoke @dry_run
Scenario: TUI launches with two-panel layout
  Given config file with defaults section
  And stdout is an interactive terminal
  When I run moondock command "run"
  Then TUI displays status panel
  And TUI displays log panel
  And status panel height is one-third of screen
  And log panel height is two-thirds of screen

@smoke @dry_run
Scenario: Status panel displays placeholder text on startup
  Given config file with defaults section
  And TUI application is running
  When TUI first launches
  Then status panel shows placeholder text for instance ID
  And status panel shows placeholder text for instance type
  And status panel shows placeholder text for region
  And status panel shows placeholder text for machine name
  And status panel shows placeholder text for command
  And status panel shows placeholder text for forwarded ports
  And status panel shows placeholder text for SSH connection

@smoke @dry_run
Scenario: Status panel updates with instance data
  Given config file with defaults section
  And TUI application is running
  When instance is launched successfully
  Then status panel shows instance ID
  And status panel shows instance type
  And status panel shows AWS region
  And status panel shows machine name
  And status panel shows command
  And status panel shows forwarded URLs
  And status panel shows SSH connection string
  And status panel shows static uptime

@smoke @dry_run
Scenario: Log panel streams log messages
  Given config file with defaults section
  And TUI application is running
  When log messages are generated
  Then log panel displays messages
  And log panel is scrollable

@smoke @dry_run
Scenario: Status panel updates from queue in sequence
  Given config file with defaults section
  And TUI application is running
  When queue receives config and instance updates
  Then status panel processes updates in order
  And widgets reflect both config and instance data
