Feature: Multi-User Isolation

@smoke @dry_run
Scenario: New instance is tagged with owner
  Given the current user's identity is "alice@example.com"
  When I run campers run to create an instance
  Then the instance has Owner tag "alice@example.com"

@smoke @dry_run
Scenario: List shows only current user's instances by default
  Given instances exist with owners "alice@example.com" and "bob@example.com"
  And the current user's identity is "alice@example.com"
  When I run list command directly
  Then output displays title "Instances for alice@example.com:"
  And only alice's instances are shown
  And output does not contain column "OWNER"

@smoke @dry_run
Scenario: List with --all flag shows all instances
  Given instances exist with owners "alice@example.com" and "bob@example.com"
  When I run list command directly with --all flag
  Then output contains columns "OWNER"
  And both users' instances are shown

@smoke @dry_run
Scenario: Fallback to USER environment variable
  Given git config user.email is not set
  And USER environment variable is "testuser"
  When I run campers run to create an instance
  Then the instance has Owner tag "testuser"

@smoke @dry_run
Scenario: Legacy instances appear in --all listing
  Given an instance exists without Owner tag
  And the instance has Name "legacy-instance"
  When I run list command directly with --all flag
  Then the instance "legacy-instance" is shown with owner "unknown"

@smoke @dry_run
Scenario: Legacy instances excluded from default listing
  Given an instance exists without Owner tag
  And the current user's identity is "alice@example.com"
  When I run list command directly
  Then the untagged instance is not shown
