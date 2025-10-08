Feature: YAML Configuration Loader

@smoke
Scenario: Load config with defaults only
  Given config file "moondock.yaml" with defaults section
  When I load configuration without machine name
  Then config contains region "us-east-1"
  And config contains instance_type "t3.medium"
  And config contains disk_size 50

@smoke
Scenario: Load config with machine override
  Given config file with defaults section
  And machine "jupyter-lab" with instance_type "m5.xlarge"
  When I load configuration for machine "jupyter-lab"
  Then config contains instance_type "m5.xlarge"
  And config contains region from defaults

@smoke
Scenario: Handle missing config file
  Given no config file exists
  When I load configuration
  Then built-in defaults are used
  And config contains region "us-east-1"

@error
Scenario: Validate required field missing
  Given config missing "region" field
  When I validate configuration
  Then ValueError is raised with "region is required"

@error
Scenario: Validate port conflict
  Given config with both "port" and "ports"
  When I validate configuration
  Then ValueError is raised with "cannot specify both port and ports"

@smoke
Scenario: Configuration hierarchy merging
  Given built-in defaults exist
  And YAML defaults override disk_size to 100
  And machine "ml-training" overrides disk_size to 200
  When I load configuration for machine "ml-training"
  Then config contains disk_size 200

@smoke
Scenario: List fields replace not merge
  Given YAML defaults with ignore ["*.pyc", "__pycache__"]
  And machine "jupyter-lab" with ignore ["*.pyc", "data/", "models/"]
  When I load configuration for machine "jupyter-lab"
  Then config ignore is ["*.pyc", "data/", "models/"]

@smoke
Scenario: Load from environment variable
  Given MOONDOCK_CONFIG is "/tmp/custom-config.yaml"
  And config file exists at "/tmp/custom-config.yaml"
  When I load configuration without path
  Then config loaded from "/tmp/custom-config.yaml"

@error
Scenario: Validate sync_paths structure
  Given config with sync_paths missing "remote" key
  When I validate configuration
  Then ValueError is raised with "sync_paths entry must have both 'local' and 'remote' keys"
