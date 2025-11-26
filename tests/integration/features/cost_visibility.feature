Feature: Cost Visibility

@smoke @mock @dry_run
Scenario: List command shows costs with mocked pricing
  Given AWS Pricing API is mocked with sample rates
  And I have a running instance of type "t3.medium"
  And I have a stopped instance of type "g5.2xlarge"
  When I run "campers list"
  Then cost column shows "$29.95/month" for t3.medium
  And cost column shows "$3.20/month" for g5.2xlarge
  And I see total estimated cost "$33.15/month"

@smoke @localstack
Scenario: List command shows pricing unavailable in LocalStack
  Given AWS Pricing API is not accessible
  And I have a running instance of type "t3.medium"
  When I run "campers list"
  Then I see "ℹ️  Pricing unavailable" at top
  And cost column shows "Pricing unavailable"
  And no total cost is displayed

@smoke @mock @dry_run
Scenario: Stop command shows cost savings with pricing
  Given AWS Pricing API is mocked with sample rates
  And I have a running instance of type "g5.2xlarge" with 100GB volume
  When I run "campers stop {instance}"
  Then I see "💰 Cost Impact"
  And I see "Previous: $871.20/month"
  And I see "New: $8.00/month"
  And I see "Savings: $863.20/month (~99% reduction)"

@smoke @localstack
Scenario: Stop command handles unavailable pricing gracefully
  Given AWS Pricing API is not accessible
  And I have a running instance
  When I run "campers stop {instance}"
  Then I see "(Cost information unavailable)"
  And stop operation completes successfully

@smoke @mock @dry_run
Scenario: Start command shows cost increase with pricing
  Given AWS Pricing API is mocked with sample rates
  And I have a stopped instance of type "t3.medium" with 50GB volume
  When I run "campers start {instance}"
  Then I see "💰 Cost Impact"
  And I see "Previous: $4.00/month"
  And I see "New: $29.95/month"
  And I see "Increase: $25.95/month"

@smoke @localstack
Scenario: Start command handles unavailable pricing gracefully
  Given AWS Pricing API is not accessible
  And I have a stopped instance
  When I run "campers start {instance}"
  Then I see "(Cost information unavailable)"
  And start operation completes successfully

@smoke @mock @dry_run
Scenario: Pricing cache prevents redundant API calls
  Given AWS Pricing API is mocked with call counter
  And I run "campers list" twice within 24 hours
  Then API is called once for each instance type
  And second list uses cached pricing

@error @mock @dry_run
Scenario: Unknown region returns None for pricing
  Given AWS Pricing API is available
  And I have a running instance of type "t3.medium"
  And I have an instance in unsupported region "ap-unknown-1"
  When I run "campers list"
  Then that instance shows "Pricing unavailable" in cost column
  And other instances show correct pricing
