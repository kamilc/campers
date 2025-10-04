Feature: Instance List Command

@smoke @dry_run
Scenario: List instances across all regions
  Given 2 moondock instances exist in "us-east-1"
  And 1 moondock instance exists in "us-west-2"
  When I run list command directly
  Then output displays 3 instances
  And output contains columns "NAME, INSTANCE-ID, STATUS, REGION, TYPE, LAUNCHED"
  And instances are sorted by launch time descending

@smoke @dry_run
Scenario: List instances filtered by region
  Given 2 moondock instances exist in "us-east-1"
  And 1 moondock instance exists in "us-west-2"
  When I run list command directly with region "us-east-1"
  Then output displays header "Instances in us-east-1:"
  And output displays 2 instances
  And output contains columns "NAME, INSTANCE-ID, STATUS, TYPE, LAUNCHED"
  And output does not contain column "REGION"

@smoke @dry_run
Scenario: No instances found
  Given no moondock instances exist
  When I run list command directly
  Then output displays "No moondock-managed instances found"

@error @dry_run @no_credentials
Scenario: AWS credentials missing
  Given no AWS credentials configured
  When I run list command directly
  Then command fails with NoCredentialsError
  And output displays "AWS credentials not found"

@smoke @dry_run
Scenario: Display instance with ad-hoc machine config
  Given instance "i-abc123" exists with no MachineConfig tag
  When I run list command directly
  Then instance "i-abc123" shows NAME as "ad-hoc"

@smoke @dry_run
Scenario: Display human-readable launch times
  Given instance launched 30 minutes ago
  And instance launched 2 hours ago
  And instance launched 5 days ago
  When I run list command directly
  Then first instance shows "30m ago"
  And second instance shows "2h ago"
  And third instance shows "5d ago"

@error @dry_run
Scenario: Handle partial region failures
  Given moondock instances exist in "us-east-1"
  And region "us-west-2" query fails with timeout
  When I run list command directly
  Then output displays instances from "us-east-1"
  And warning logged for region "us-west-2"

@smoke @dry_run
Scenario: Display instances in various states
  Given instance "i-abc" in state "running"
  And instance "i-def" in state "stopped"
  And instance "i-ghi" in state "stopping"
  When I run list command directly
  Then all 3 instances are displayed
  And STATUS column shows correct state for each instance

@smoke @dry_run
Scenario: Handle long machine config names
  Given instance with MachineConfig "very-long-machine-config-name-exceeds-column-width"
  When I run list command directly
  Then machine config name is truncated to 19 characters
  And table formatting remains aligned

@smoke @dry_run
Scenario: Empty state with region filter
  Given no moondock instances exist in "us-east-1"
  When I run list command directly with region "us-east-1"
  Then output displays "No moondock-managed instances found"
  And no header is printed
  And no table is printed

@error @dry_run
Scenario: Fallback to default region when describe_regions fails
  Given moondock instances exist in "us-east-1"
  And describe_regions call fails
  When I run list command directly
  Then output displays instances from "us-east-1"
  And warning logged for describe_regions failure
