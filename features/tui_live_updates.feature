Feature: TUI Live Updates and Interactivity

@smoke @dry_run
Scenario: Status panel updates through all instance states
  Given config file with defaults section
  And TUI application is running
  When status update event "launching" is received
  Then status widget displays "launching"
  When status update event "running" is received
  Then status widget displays "running"
  When status update event "terminating" is received
  Then status widget displays "terminating"

@smoke @dry_run
Scenario: Uptime counter updates every second
  Given config file with defaults section
  And TUI application is running
  When uptime timer ticks 3 times
  Then uptime widget displays time elapsed

@smoke @dry_run
Scenario: Mutagen widget displays sync state and file count
  Given config file with defaults section
  And TUI application is running
  When mutagen status event with state "syncing" and 42 files is received
  Then mutagen widget displays state "syncing"
  And mutagen widget displays "42 files"
  When mutagen status event with state "error" is received
  Then mutagen widget displays state "error"

@smoke @dry_run
Scenario: Mutagen widget displays not syncing when unconfigured
  Given config file without sync_paths configuration
  And TUI application is running
  When TUI first launches
  Then mutagen widget displays "Not syncing"

@smoke @dry_run
Scenario: Press q key initiates graceful shutdown
  Given config file with defaults section
  And TUI application is running
  When user presses "q" key
  Then graceful shutdown is initiated

@smoke @dry_run
Scenario: Second Ctrl+C within 1.5 seconds forces immediate exit
  Given config file with defaults section
  And TUI application is running
  When first SIGINT signal is received
  And second SIGINT signal is received within 1.5 seconds
  Then application exits immediately
