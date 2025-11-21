Feature: TUI Warn about Sensitive Variables

@smoke @localstack @timeout_60
Scenario: Warn about sensitive variables
  Given a config file with machine "myproject" defined
  And machine "myproject" has command "exit 42"
  And LocalStack is healthy and responding
  And local environment has AWS_SECRET_ACCESS_KEY and OPENAI_API_KEY
  And config has env_filter [".*SECRET.*", ".*_API_KEY$"]
  And stdout is an interactive terminal
  When I launch the Moondock TUI with the config file
  And I simulate running the "myproject" in the TUI
  Then the TUI log panel contains "Forwarding sensitive environment variables"
  And the TUI log panel contains "Command completed with exit code: 42"
