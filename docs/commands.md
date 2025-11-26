# Commands

Complete reference for all Campers CLI commands.

## run

Launch an EC2 instance with file sync and command execution.

```bash
campers run [CAMP_NAME] [OPTIONS]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `CAMP_NAME` | Name of camp from configuration (optional) |

### Options

| Option | Description |
|--------|-------------|
| `-c`, `--command` | Command to execute |
| `--instance-type` | Override EC2 instance type |
| `--disk-size` | Override root volume size (GB) |
| `--region` | Override AWS region |
| `--port` | Additional port to forward |
| `--plain` | Disable TUI, use plain text output |

### Examples

```bash
# Use defaults
campers run

# Use a named camp
campers run jupyter

# Override settings
campers run --instance-type t3.large --disk-size 100

# Execute a specific command
campers run dev -c "python train.py"

# Plain text output (no TUI)
campers run --plain
```

## list

Display all Campers-managed instances across regions.

```bash
campers list [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--region` | Filter by AWS region |
| `--json` | Output as JSON |

### Examples

```bash
# List all instances
campers list

# Filter by region
campers list --region us-west-2

# JSON output for scripting
campers list --json
```

### Output

```
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Name               ┃ Instance ID  ┃ State      ┃ Region         ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ campers-myproj-main│ i-0abc123def │ running    │ us-east-1      │
│ campers-myproj-dev │ i-0def456abc │ stopped    │ us-east-1      │
└────────────────────┴──────────────┴────────────┴────────────────┘
```

## stop

Stop a running instance. The instance and its data are preserved.

```bash
campers stop <TARGET>
```

### Arguments

| Argument | Description |
|----------|-------------|
| `TARGET` | Instance name or ID |

### Examples

```bash
# Stop by name
campers stop dev

# Stop by instance ID
campers stop i-0abc123def456
```

!!! note
    Stopped instances do not incur compute charges, but EBS volumes still incur storage charges.

## start

Start a previously stopped instance.

```bash
campers start <TARGET>
```

### Arguments

| Argument | Description |
|----------|-------------|
| `TARGET` | Instance name or ID |

### Examples

```bash
# Start by name
campers start dev

# Start by instance ID
campers start i-0abc123def456
```

After starting, use `campers run` to reconnect with file sync:

```bash
campers start dev
campers run dev
```

## destroy

Terminate an instance and delete associated resources (key pair, security group).

```bash
campers destroy <TARGET> [OPTIONS]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `TARGET` | Instance name or ID |

### Options

| Option | Description |
|--------|-------------|
| `--force` | Skip confirmation prompt |

### Examples

```bash
# Destroy by name
campers destroy dev

# Destroy by instance ID
campers destroy i-0abc123def456

# Skip confirmation
campers destroy dev --force
```

!!! danger "Warning"
    This permanently deletes the instance and all data on its volumes. This action cannot be undone.

## init

Generate a starter configuration file.

```bash
campers init [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--force` | Overwrite existing configuration |

### Examples

```bash
# Generate campers.yaml
campers init

# Overwrite existing config
campers init --force
```

## doctor

Verify AWS credentials and required IAM permissions.

```bash
campers doctor
```

### Checks Performed

- AWS credentials are configured
- IAM permissions for EC2 operations
- Mutagen is installed
- Network connectivity to AWS

### Example Output

```
Checking AWS credentials... OK
Checking IAM permissions... OK
Checking Mutagen installation... OK
All checks passed!
```

## setup

Create required AWS resources (VPC, security groups) for a region.

```bash
campers setup [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--region` | AWS region to set up |

### Examples

```bash
# Set up default region
campers setup

# Set up specific region
campers setup --region eu-west-1
```

### Resources Created

- Default VPC (if not exists)
- Security group with SSH access
- Required IAM resources

## Global Options

These options work with all commands:

| Option | Description |
|--------|-------------|
| `--help` | Show help message |
| `--version` | Show version number |

## Exit Codes

| Code | Description |
|------|-------------|
| `0` | Success |
| `1` | General error |
| `2` | Configuration error |
| `130` | Interrupted (Ctrl+C) |
