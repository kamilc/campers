Feature: Environment Variable Forwarding

@smoke @dry_run
Scenario: Forward AWS credentials to remote command
  Given local environment has AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
  And config has env_filter ["AWS_.*"]
  When I run moondock command "run -c 'aws s3 ls'"
  Then 2 environment variables are forwarded
  And command executes with export prefix
  And AWS credentials are available in remote command

@smoke @dry_run
Scenario: Forward multiple token types
  Given local environment has AWS_ACCESS_KEY_ID, HF_TOKEN, WANDB_API_KEY
  And config has env_filter ["AWS_.*", "HF_TOKEN", ".*_API_KEY$"]
  When I run moondock command "run -c 'env'"
  Then 3 environment variables are forwarded
  And status message "Forwarding 3 environment variables" is logged

@smoke @dry_run
Scenario: No env_filter configured
  Given config has no env_filter defined
  When I run moondock command "run -c 'echo test'"
  Then no environment variables are forwarded
  And command executes without export prefix

@smoke @dry_run
Scenario: Empty env_filter list
  Given config has env_filter []
  When I run moondock command "run -c 'echo test'"
  Then no environment variables are forwarded
  And command executes without export prefix

@error @dry_run
Scenario: Shell injection prevention
  Given local environment has MALICIOUS_VAR with value "'; rm -rf / #"
  And config has env_filter ["MALICIOUS_.*"]
  When environment variables are filtered
  Then variable value is properly escaped with shlex.quote()
  And shell injection is prevented

@error @dry_run
Scenario: Invalid regex pattern validation
  Given config has env_filter ["AWS_.*", "[invalid(regex"]
  When config validation runs
  Then ValueError is raised
  And error message contains "Invalid regex pattern in env_filter"

@smoke @dry_run
Scenario: Test mode simulates environment forwarding
  Given MOONDOCK_TEST_MODE is "1"
  And config has env_filter ["AWS_.*", "HF_TOKEN"]
  When I run moondock command "run -c 'echo test'"
  Then status message "Forwarding" is logged
  And test completes successfully

@smoke @dry_run
Scenario: Warn about sensitive variables
  Given local environment has AWS_SECRET_ACCESS_KEY and OPENAI_API_KEY
  And config has env_filter [".*SECRET.*", ".*_API_KEY$"]
  When environment variables are filtered
  Then warning message "Forwarding sensitive environment variables" is logged
  And variables are still forwarded
