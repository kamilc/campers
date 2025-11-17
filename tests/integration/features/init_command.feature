Feature: Init Command

@smoke
Scenario: Create config at default location
  Given "moondock.yaml" does not exist
  And MOONDOCK_CONFIG is not set
  When I run init command
  Then "moondock.yaml" is created
  And file contains template content
  And success message includes "moondock.yaml"

@smoke
Scenario: Create config at custom location via environment variable
  Given MOONDOCK_CONFIG is "/tmp/custom.yaml"
  And "/tmp/custom.yaml" does not exist
  When I run init command
  Then "/tmp/custom.yaml" is created
  And file contains template content
  And success message includes "/tmp/custom.yaml"

@smoke
Scenario: Create config with parent directory creation
  Given MOONDOCK_CONFIG is "configs/project/moondock.yaml"
  And "configs/project/" does not exist
  When I run init command
  Then "configs/project/" directory is created
  And "configs/project/moondock.yaml" is created
  And file contains template content
  And success message includes "configs/project/moondock.yaml"

@error
Scenario: Refuse to overwrite existing config without force
  Given "moondock.yaml" exists
  And MOONDOCK_CONFIG is not set
  When I run init command
  Then command fails with exit code 1
  And "moondock.yaml" is not modified
  And error message includes "moondock.yaml"
  And error is printed to stderr

@smoke
Scenario: Overwrite existing config with force flag
  Given "moondock.yaml" exists
  And MOONDOCK_CONFIG is not set
  When I run init command with "--force"
  Then "moondock.yaml" is overwritten
  And file contains template content
  And success message includes "moondock.yaml"
