Feature: CLI Option Parsing and Config Merging

@smoke
Scenario: Run with machine name only
  Given config file with machine "jupyter-lab" defined
  And machine "jupyter-lab" has instance_type "m5.xlarge"
  When I run moondock command "run jupyter-lab"
  Then final config contains instance_type "m5.xlarge"
  And final config contains defaults for unspecified fields

@smoke
Scenario: Run with machine name and CLI overrides
  Given config file with machine "dev-workstation" defined
  And machine "dev-workstation" has instance_type "t3.large"
  And machine "dev-workstation" has disk_size 100
  When I run moondock command "run dev-workstation --instance-type m5.2xlarge --region us-west-2"
  Then final config contains instance_type "m5.2xlarge"
  And final config contains region "us-west-2"
  And final config contains disk_size 100

@smoke
Scenario: Run with defaults and CLI options
  Given config file with defaults section only
  When I run moondock command "run --instance-type t3.large --disk-size 200 --region us-east-2"
  Then final config contains instance_type "t3.large"
  And final config contains disk_size 200
  And final config contains region "us-east-2"

@smoke
Scenario: Run with command override
  Given config file with machine "jupyter-lab" defined
  And machine "jupyter-lab" has command "jupyter notebook"
  When I run moondock command "run jupyter-lab --command 'jupyter lab --port=8890'"
  Then final config contains command "jupyter lab --port=8890"

@smoke
Scenario: Multiple port forwarding
  Given config file with defaults section
  When I run moondock command "run --port 8888,6006,5000"
  Then final config contains ports [8888, 6006, 5000]
  And final config does not contain "port" field

@smoke
Scenario: Comma-separated ignore patterns
  Given config file with defaults section
  When I run moondock command "run --ignore '*.pyc,data/,models/,__pycache__'"
  Then final config contains ignore ["*.pyc", "data/", "models/", "__pycache__"]

@smoke
Scenario: Include VCS boolean conversion
  Given config file with defaults section
  When I run moondock command "run --include-vcs true"
  Then final config contains include_vcs True

@error
Scenario: Invalid machine name error
  Given config file with machines ["dev-workstation", "jupyter-lab"]
  When I run moondock command "run nonexistent-machine"
  Then command fails with ValueError
  And error message contains "Machine 'nonexistent-machine' not found"

@error
Scenario: Invalid include_vcs value
  Given config file with defaults section
  When I run moondock command "run --include-vcs yes"
  Then command fails with ValueError
  And error message contains "include_vcs must be 'true' or 'false'"

@smoke
Scenario: CLI options override config hierarchy
  Given YAML defaults with region "us-west-1"
  And machine "ml-training" overrides region to "eu-west-1"
  When I run moondock command "run ml-training --region ap-southeast-1"
  Then final config contains region "ap-southeast-1"

@smoke
Scenario: Run with no machine name and no CLI options
  Given config file with defaults section
  And defaults section has region "us-west-1"
  When I run moondock command "run"
  Then final config contains region "us-west-1"
  And final config contains built-in defaults for other fields

@smoke
Scenario: Run without command specified
  Given config file with machine "dev-workstation" defined
  And machine "dev-workstation" has no command field
  When I run moondock command "run dev-workstation"
  Then final config does not contain command field
  And validation passes

@smoke
Scenario: Config-file-only fields preserved
  Given config file with machine "jupyter-lab" defined
  And machine "jupyter-lab" has setup_script "install.sh"
  And machine "jupyter-lab" has startup_script "start.sh"
  And machine "jupyter-lab" has env_filter "AWS_.*"
  When I run moondock command "run jupyter-lab --instance-type m5.xlarge"
  Then final config contains instance_type "m5.xlarge"
  And final config contains setup_script "install.sh"
  And final config contains startup_script "start.sh"
  And final config contains env_filter "AWS_.*"
