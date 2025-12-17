Feature: Session File Infrastructure

Session files enable fast instance discovery by caching SSH connection details with PID-based liveness checking.

@dry_run @smoke
Scenario: Create session file with valid SessionInfo
  Given a SessionManager with temporary sessions directory
  And SessionInfo for camp "dev" with pid of current process
  When I create a session
  Then session file exists at "dev.session.json"
  And session file contains valid JSON
  And session file contains all required fields

@dry_run @smoke
Scenario: Delete session file
  Given a SessionManager with temporary sessions directory
  And session file exists for camp "dev"
  When I delete the session for "dev"
  Then session file does not exist for "dev"

@dry_run @smoke
Scenario: Delete non-existent session file does not raise error
  Given a SessionManager with temporary sessions directory
  When I delete the session for "nonexistent"
  Then no error is raised

@dry_run @smoke
Scenario: Read existing session file
  Given a SessionManager with temporary sessions directory
  And session file exists for camp "dev" with valid JSON
  When I read the session for "dev"
  Then result is a SessionInfo object
  And SessionInfo has correct camp_name "dev"

@dry_run @smoke
Scenario: Read non-existent session file returns None
  Given a SessionManager with temporary sessions directory
  When I read the session for "nonexistent"
  Then result is None

@dry_run @error
Scenario: Read malformed session file returns None
  Given a SessionManager with temporary sessions directory
  And session file exists for camp "dev" with invalid JSON
  When I read the session for "dev"
  Then result is None

@dry_run @smoke
Scenario: Is session alive with running process
  Given a SessionManager with temporary sessions directory
  And session file exists for camp "dev" with pid of current process
  When I check if session is alive for "dev"
  Then result is True

@dry_run @smoke
Scenario: Is session alive with non-existent process
  Given a SessionManager with temporary sessions directory
  And session file exists for camp "dev" with pid 99999
  When I check if session is alive for "dev"
  Then result is False
  And session file does not exist for "dev"

@dry_run @smoke
Scenario: Is session alive with missing session file returns False
  Given a SessionManager with temporary sessions directory
  When I check if session is alive for "nonexistent"
  Then result is False

@dry_run @smoke
Scenario: Get alive session with running process
  Given a SessionManager with temporary sessions directory
  And session file exists for camp "dev" with pid of current process
  When I get alive session for "dev"
  Then result is a SessionInfo object
  And SessionInfo has correct camp_name "dev"

@dry_run @smoke
Scenario: Get alive session with non-existent process returns None and cleans up
  Given a SessionManager with temporary sessions directory
  And session file exists for camp "dev" with pid 99999
  When I get alive session for "dev"
  Then result is None
  And session file does not exist for "dev"

@dry_run @smoke
Scenario: Get alive session with missing session file returns None
  Given a SessionManager with temporary sessions directory
  When I get alive session for "nonexistent"
  Then result is None

@dry_run @smoke
Scenario: Respect CAMPERS_DIR environment variable
  Given CAMPERS_DIR is set to a temporary directory
  And a SessionManager with default initialization
  And SessionInfo for camp "dev" with pid of current process
  When I create a session
  Then session file exists at CAMPERS_DIR/sessions/dev.session.json

@dry_run @smoke
Scenario: Atomic write creates sessions directory
  Given a SessionManager with temporary sessions directory that does not exist
  And SessionInfo for camp "dev" with pid of current process
  When I create a session
  Then sessions directory is created
  And session file exists at "dev.session.json"

@dry_run @error
Scenario: Session file contains all required fields
  Given a SessionManager with temporary sessions directory
  And SessionInfo for camp "dev" with pid 12345 and region "us-east-1"
  When I create a session
  And I read the session for "dev"
  Then result contains camp_name "dev"
  And result contains pid 12345
  And result contains region "us-east-1"
  And result contains instance_id
  And result contains ssh_host
  And result contains ssh_port
  And result contains ssh_user
  And result contains key_file
