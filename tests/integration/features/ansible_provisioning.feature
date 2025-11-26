Feature: Ansible Provisioning

@smoke @integration
Scenario: Execute single Ansible playbook
  Given config with playbook "system_setup" defined
  And camp "webserver" has ansible_playbook "system_setup"
  When I launch instance with camp "webserver"
  Then playbook "system_setup" is executed on instance
  And Ansible output is logged
  And temporary files are cleaned up

@smoke @integration
Scenario: Execute multiple Ansible playbooks in sequence
  Given config with playbooks "base" and "webapp" defined
  And camp "webserver" has ansible_playbooks ["base", "webapp"]
  When I launch instance with camp "webserver"
  Then playbook "base" is executed first
  And playbook "webapp" is executed second
  And both playbooks succeed

@error @dry_run
Scenario: Error when Ansible not installed locally
  Given Ansible is not installed on local camp
  And config has ansible_playbook "system_setup" defined
  When I attempt to launch instance
  Then command fails with RuntimeError
  And error message contains "pip install ansible"

@error @dry_run
Scenario: Error when playbook name not found
  Given Ansible is installed on local camp
  And config has no "missing_playbook" defined
  And camp has ansible_playbook "missing_playbook"
  When I attempt to launch instance
  Then command fails with ValueError
  And error message lists available playbooks

@error @dry_run
Scenario: Error when ansible_playbook but no playbooks section
  Given Ansible is installed on local camp
  And config has no "playbooks" section
  And camp has ansible_playbook "test"
  When I attempt to launch instance
  Then command fails with ValueError
  And error message mentions playbooks section

@smoke @dry_run
Scenario: Ansible playbook with variable substitution
  Given config with vars section defining "nginx_port"
  And playbook uses variable "${nginx_port}"
  When configuration is loaded
  Then variable is resolved in playbook

@integration
Scenario: Full workflow with Ansible provisioning
  Given LocalStack is running
  And Ansible is installed on local camp
  And config with playbook "webapp" defined
  And camp "webserver" with ansible_playbook "webapp"
  When I launch instance via CLI
  Then instance launches successfully
  And Mutagen sync completes
  And Ansible playbook executes
  And startup_script runs
  And instance terminates cleanly

@smoke @dry_run
Scenario: Ansible with custom ssh_username
  Given config with ssh_username "ec2-user"
  And playbook "system_setup" defined
  When I validate configuration
  Then ssh_username validation succeeds
  And Ansible would connect as "ec2-user"

@error @dry_run
Scenario: Error when both ansible_playbook and ansible_playbooks specified
  Given camp config has ansible_playbook "test"
  And camp config also has ansible_playbooks ["test"]
  When I validate configuration
  Then ValueError is raised
  And error message explains mutual exclusivity

@error @dry_run
Scenario: Invalid ssh_username format
  Given config with ssh_username "User@Host"
  When I validate configuration
  Then ValueError is raised
  And error message contains "Invalid ssh_username"
