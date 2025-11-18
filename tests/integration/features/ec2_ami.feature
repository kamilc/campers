Feature: EC2 AMI Selection

@smoke @dry_run
Scenario: Direct AMI ID specification returns AMI without query
  Given a config with ami.image_id set to "ami-0abc123def456"
  When AMI is resolved
  Then the AMI ID "ami-0abc123def456" is returned
  And no AWS describe_images call is made

@smoke @dry_run
Scenario: Query for latest Ubuntu AMI with name and owner filters
  Given a config with ami.query.name set to "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"
  And ami.query.owner set to "099720109477"
  When AMI is resolved
  Then describe_images is called with name and owner filters
  And the newest AMI by CreationDate is returned

@smoke @dry_run
Scenario: Query with architecture filter
  Given a config with ami.query.name set to "Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04) ????????"
  And ami.query.owner set to "amazon"
  And ami.query.architecture set to "x86_64"
  When AMI is resolved
  Then describe_images is called with name, owner, and architecture filters
  And the newest matching AMI is returned

@smoke @dry_run
Scenario: Query without owner filter searches all owners
  Given a config with ami.query.name set to "company-custom-*"
  And no ami.query.owner specified
  When AMI is resolved
  Then describe_images is called without Owners parameter
  And the newest matching AMI from any owner is returned

@smoke @dry_run
Scenario: Default Amazon Ubuntu 24 when no ami section
  Given a config with no ami section
  When AMI is resolved
  Then Amazon Ubuntu 24 x86_64 is queried with Amazon owner
  And the newest AMI is returned

@error @dry_run
Scenario: Error when both image_id and query specified
  Given a config with both ami.image_id and ami.query specified
  When AMI resolution is attempted
  Then ValueError is raised
  And error message contains "Cannot specify both"

@error @dry_run
Scenario: Error when AMI ID format invalid
  Given a config with ami.image_id set to "invalid-ami-id"
  When AMI resolution is attempted
  Then ValueError is raised
  And error message contains "Invalid AMI ID format"

@error @dry_run
Scenario: Error when query.name missing
  Given a config with ami.query but no name field
  When AMI resolution is attempted
  Then ValueError is raised
  And error message contains "ami.query.name is required"

@error @dry_run
Scenario: Error when architecture invalid
  Given a config with ami.query.architecture set to "amd64"
  When AMI resolution is attempted
  Then ValueError is raised
  And error message contains "Invalid architecture"
  And error message lists valid architectures

@error @dry_run
Scenario: Error when no AMIs match query
  Given a config with ami.query filters that match no AMIs
  When AMI resolution is attempted
  Then ValueError is raised
  And error message includes all filter values

@smoke @dry_run
Scenario: Backward compatibility - existing config without ami section
  Given an existing moondock config without ami section
  When instance is launched
  Then Amazon Ubuntu 24 x86_64 AMI is selected
  And behavior is unchanged from previous version
