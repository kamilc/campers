Feature: Init Command

@smoke
Scenario: Create config at default location
  Given "campers.yaml" does not exist
  And CAMPERS_CONFIG is not set
  When I run init command
  Then "campers.yaml" is created
  And file contains template content
  And success message includes "campers.yaml"

@smoke
Scenario: Create config at custom location via environment variable
  Given CAMPERS_CONFIG is "/tmp/custom.yaml"
  And "/tmp/custom.yaml" does not exist
  When I run init command
  Then "/tmp/custom.yaml" is created
  And file contains template content
  And success message includes "/tmp/custom.yaml"

@smoke
Scenario: Create config with parent directory creation
  Given CAMPERS_CONFIG is "configs/project/campers.yaml"
  And "configs/project/" does not exist
  When I run init command
  Then "configs/project/" directory is created
  And "configs/project/campers.yaml" is created
  And file contains template content
  And success message includes "configs/project/campers.yaml"

@error
Scenario: Refuse to overwrite existing config without force
  Given "campers.yaml" exists
  And CAMPERS_CONFIG is not set
  When I run init command
  Then command fails with exit code 1
  And "campers.yaml" is not modified
  And error message includes "campers.yaml"
  And error is printed to stderr

@smoke
Scenario: Overwrite existing config with force flag
  Given "campers.yaml" exists
  And CAMPERS_CONFIG is not set
  When I run init command with "--force"
  Then "campers.yaml" is overwritten
  And file contains template content
  And success message includes "campers.yaml"
