Feature: TUI Instance Overview Widget

@smoke @localstack
Scenario: Widget displays correct counts
  Given I have 2 running instances
  And I have 3 stopped instances
  When I view the TUI
  Then overview widget shows "Instances - Running: 2  Stopped: 3  N/A"

@smoke @localstack
Scenario: Widget handles empty instance list
  Given I have 0 instances
  When I view the TUI
  Then overview widget shows "Instances - Running: 0  Stopped: 0  N/A"

@smoke @localstack
Scenario: Widget handles EC2 API errors gracefully
  Given TUI is displaying "Instances - Running: 2  Stopped: 1  N/A"
  When EC2 API fails
  And 30 seconds pass
  Then overview widget shows "Instances - Running: 2  Stopped: 1  N/A"
  And no error is shown to user

@smoke @localstack
Scenario: Widget queries all regions
  Given I have 1 running instance in us-east-1
  And I have 2 stopped instances in us-west-2
  When I view the TUI
  Then overview widget shows "Instances - Running: 1  Stopped: 2  N/A"

@smoke @localstack
Scenario: Widget refreshes every 30 seconds
  Given TUI is displaying "Instances - Running: 1  Stopped: 0  N/A"
  When I launch a new instance
  And 35 seconds pass
  And the widget refreshes
  Then overview widget shows "Instances - Running: 2  Stopped: 0  N/A"

@smoke @mock
Scenario: Widget displays cost when pricing available
  Given I have 1 running t3.medium instance
  And AWS Pricing API is mocked with sample rates
  When I view the TUI
  Then overview widget shows "Instances - Running: 1  Stopped: 0  $1.00/day"

@smoke @mock
Scenario: Widget aggregates costs across multiple instances
  Given I have 2 running t3.medium instances
  And AWS Pricing API is mocked with sample rates
  When I view the TUI
  Then overview widget daily cost is approximately $2.00
