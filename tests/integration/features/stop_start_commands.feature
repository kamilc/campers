Feature: Stop and Start Instance Commands

@smoke @localstack
Scenario: Stop running instance transitions to stopped
  Given a running instance with name "campers-myproject-main"
  When I run "campers stop campers-myproject-main"
  Then the instance state is "stopped"
  And the instance public IP is None
  And the security group is preserved
  And the key pair is preserved

@smoke @localstack
Scenario: Start stopped instance transitions to running
  Given a stopped instance with name "campers-myproject-main"
  And the stopped instance has public IP None
  When I run "campers start campers-myproject-main"
  Then the instance state is "running"
  And the instance has a new public IP
  And the public IP is different from before stopping

@smoke @localstack
Scenario: Stop command is idempotent for already stopped instance
  Given a stopped instance with name "campers-myproject-main"
  When I run "campers stop campers-myproject-main"
  Then the command succeeds
  And I see message "Instance already stopped"

@smoke @localstack
Scenario: Start command is idempotent for already running instance
  Given a running instance with name "campers-myproject-main"
  When I run "campers start campers-myproject-main"
  Then the command succeeds
  And I see message "Instance already running"
  And I see the current public IP

@error @localstack
Scenario: Stop command fails when instance not found
  When I run "campers stop non-existent-instance"
  Then the command fails
  And error message includes "No campers-managed instances matched"

@error @localstack
Scenario: Start command fails when instance not found
  When I run "campers start non-existent-instance"
  Then the command fails
  And error message includes "No campers-managed instances matched"
