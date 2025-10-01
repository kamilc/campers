Feature: EC2 AMI Selection

@smoke @dry_run
Scenario: Lookup Ubuntu 22.04 AMI in region
  Given region "us-east-1"
  When I lookup Ubuntu 22.04 AMI
  Then AMI is from Canonical owner "123456789012"
  And AMI architecture is "x86_64"
  And AMI virtualization is "hvm"
  And AMI is most recent available

@error @dry_run
Scenario: AMI not found in region
  Given region with no Ubuntu 22.04 AMI
  When I attempt to lookup AMI
  Then command fails with ValueError
  And error message contains "No Ubuntu 22.04 AMI found"
