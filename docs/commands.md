# Commands

Complete reference for all Campers CLI commands.

## run

The primary command. It provisions, syncs, and connects you to the camp.

```bash
campers run [CAMP_NAME] [OPTIONS]
```

**Behavior:**
1.  **Provision:** If the instance doesn't exist, it creates it using the configuration (AMI, instance type).
2.  **Start:** If the instance exists but is stopped, it starts it.
3.  **Sync:** It establishes the **Mutagen** file sync session. This runs in the background.
4.  **Tunnel:** It sets up SSH port forwarding for all ports defined in `campers.yml`.
5.  **Connect:** It opens an interactive SSH shell (or runs the specified `--command`).

### TUI (Terminal User Interface)
By default, `run` opens a dashboard showing:
- **Sync Status:** Real-time count of files synced.
- **Logs:** Output from startup scripts and provisioning.
- **Instance Stats:** IP address, region, uptime, and cost estimates.

### Options

| Option | Description | Rationale |
|--------|-------------|-----------|
| `CAMP_NAME` | Name of the camp in `campers.yml`. Defaults to `default` if omitted. | Allows managing multiple environments (e.g., `dev`, `gpu`, `test`) from one config. |
| `-c`, `--command` | Command to execute instead of opening a shell. | Useful for "fire and forget" tasks like `campers run training -c "python train.py"`. |
| `--instance-type` | Override EC2 instance type (e.g., `c6a.xlarge`). | Quickly scale up without editing the config file. |
| `--disk-size` | Override root volume size (GB). | Need more space for a specific dataset? Override it here. |
| `--region` | Override AWS region. | Deploy closer to your data or where spot prices are lower. |
| `--port` | Additional port(s) to forward. | Expose a new service (e.g., debug port) ad-hoc. |
| `--ignore` | Comma-separated patterns to exclude from sync (e.g., `"*.log,node_modules"`). | Override config ignore patterns for this run. |
| `--plain` | Disable the TUI and use simple text output. | **Critical for CI/CD.** Use this when running in GitHub Actions or scripts. |

## list

Show instances managed by Campers across all regions.

```bash
campers list [OPTIONS]
```

**Default behavior:** Shows only your instances (filtered by your git email or username).

**What it shows:**
- **Name:** Instance name derived from project/branch/camp.
- **Status:** Running, Stopped, or Terminated.
- **Cost:** Estimated monthly cost (Compute + Storage).
- **Region:** Where the instance lives.

### Options

| Option | Description |
|--------|-------------|
| `--all` | Show all Campers instances (all users). Adds an **Owner** column. |
| `--region` | Filter to a specific AWS region. |
| `--json` | Output in JSON format for programmatic use. |

### Multi-User Filtering

By default, `campers list` shows only instances you own:

```bash
$ campers list
Instances for alice@example.com:
NAME          INSTANCE-ID      STATUS    REGION       COST/MONTH
mycamp        i-0abc123def     running   us-east-1    $30.37/month
```

Use `--all` to see everyone's instances:

```bash
$ campers list --all
NAME          INSTANCE-ID      STATUS    OWNER                REGION       COST/MONTH
mycamp        i-0abc123def     running   alice@example.com    us-east-1    $30.37/month
othercamp     i-0def456abc     stopped   bob@example.com      us-west-2    $0.00/month
```

### JSON Output

The `--json` flag outputs structured data for scripting:

```bash
campers list --json | jq '.[] | select(.state == "running")'
```

## stop

Stops the instance but **preserves the disk**.

```bash
campers stop <NAME_OR_ID> [--region REGION]
```

*   **Accepts:** Instance name (e.g., `dev`) or instance ID (e.g., `i-0abc123def456`).
*   **Cost:** You stop paying for EC2 compute (hourly rate). You **continue paying** for EBS storage (~$0.08/GB/month).
*   **Use Case:** "I'm done for the day, but I want to resume exactly where I left off tomorrow."
*   **Behind the Scenes:** Calls AWS `StopInstances`. The IP address will change upon restart.

**Cost Savings:** After stopping, Campers shows your savings:

```
Savings: $29.95/month (~95% reduction)
```

## start

Starts a previously stopped instance.

```bash
campers start <NAME_OR_ID> [--region REGION]
```

*   **Accepts:** Instance name (e.g., `dev`) or instance ID (e.g., `i-0abc123def456`).
*   **Use Case:** Resuming work on a stopped camp.
*   **Note:** You usually don't need to run this manually. `campers run` automatically starts stopped instances.

## destroy

Terminates the instance and **deletes the disk**.

```bash
campers destroy <NAME_OR_ID> [--region REGION]
```

*   **Accepts:** Instance name (e.g., `dev`) or instance ID (e.g., `i-0abc123def456`).
*   **Cost:** All billing stops immediately.
*   **Use Case:** "Task complete. I don't need this environment or its data anymore."
*   **Safety:** It asks for confirmation unless you pass `--force`.

## exec

Execute a command on a running instance without going through the full `campers run` lifecycle.

```bash
campers exec <CAMP_OR_INSTANCE> <COMMAND> [OPTIONS]
```

**Behavior:**

Think of it like `docker exec`. When you have a camp running (via `campers run` in another terminal), you can open additional shells or run one-off commands without syncing files or re-provisioning.

*   **Fast Path:** If `campers run` is active for this camp, exec uses cached connection info (~instant).
*   **Slow Path:** If no active session, exec discovers the instance via AWS API (~2-5 seconds).

### Options

| Option | Description |
|--------|-------------|
| `-it` | Interactive mode with TTY allocation (like `docker exec -it`). |
| `-i`, `--interactive` | Keep stdin open for interactive input. |
| `-t`, `--tty` | Allocate a pseudo-terminal. |
| `--region` | Narrow AWS discovery to a specific region. |

### Examples

**Run a one-off command:**

```bash
campers exec dev "ls -la"
campers exec dev "python --version"
```

**Open an interactive shell:**

```bash
campers exec dev "/bin/bash" -it
```

**Debug a running process:**

```bash
campers exec dev "htop" -it
campers exec dev "tail -f /var/log/app.log"
```

**Use instance ID directly:**

```bash
campers exec i-0abc123def456 "whoami"
```

### Use Cases

*   **Quick debugging:** Check logs, inspect files, or run diagnostics without interrupting your main session.
*   **Multiple terminals:** Open several shells to the same instance (one for logs, one for editing, one for running commands).
*   **One-off commands:** Run a quick script or check status without the overhead of full provisioning.

### Exit Codes

The exit code from the remote command is propagated. If you run `campers exec dev "exit 42"`, campers exits with code 42.

## init

Creates a `campers.yaml` starter file in the current directory.

```bash
campers init
```

*   **Rationale:** Gets you started with best-practice defaults (git ignore patterns, sensible instance types).

## doctor

Diagnose common issues.

```bash
campers doctor
```

**Checks:**
1.  **AWS Credentials:** Can we talk to the AWS API?
2.  **IAM Permissions:** Do we have rights to create instances/VPCs?
3.  **Mutagen:** Is the sync tool installed and reachable?
4.  **Network:** Can we reach the AWS endpoints?

*   **Use Case:** Run this first if `campers run` is failing mysteriously.

## setup

One-time setup helper for AWS account prerequisites.

```bash
campers setup --region us-east-1
```

**What it does:**
1.  Creates a **Default VPC** if one is missing (Campers requires a VPC).
2.  Creates/Verifies the **Security Group** allowing SSH access.

*   **Rationale:** Campers tries to be "zero-config," but AWS accounts (especially new ones) might lack basic networking. This command fixes that.

## validate

Validate your configuration file without running anything.

```bash
campers validate [CAMP_NAME]
```

**Behavior:**

*   Without `CAMP_NAME`: Validates all camps in the config file.
*   With `CAMP_NAME`: Validates only the specified camp.

**Use Cases:**

*   **CI/CD:** Check config validity before deployment.
*   **Debugging:** Verify configuration changes before running.

**Example:**

```bash
$ campers validate
✓ Configuration valid
  Camps: dev, gpu, training
```

```bash
$ campers validate dev
✓ Camp 'dev' configuration valid
```

*   **Exit Codes:** Returns `0` on success, `2` on configuration error.

## info

Display detailed information about a specific instance.

```bash
campers info <NAME_OR_ID> [--region REGION]
```

**Accepts:** Instance name (e.g., `dev`) or instance ID (e.g., `i-0abc123def456`).

**What it shows:**

*   Instance ID, state, type, and region
*   Launch time and uptime
*   Key file path for SSH access
*   Public ports with access URLs

**Example:**

```bash
$ campers info dev
Instance:    i-0abc123def456
State:       running
Type:        t3.medium
Region:      us-east-1
Launched:    2024-01-15 10:30:00
Uptime:      2h 15m
Key File:    ~/.campers/keys/abc123.pem

Public Ports:
  http://1.2.3.4:8888
  https://1.2.3.4:443
```

*   **Use Case:** Quick reference for SSH access or sharing URLs with teammates.

## Global Options

These options apply to most commands (especially `run`).

| Option | Description |
|--------|-------------|
| `-v`, `--verbose` | Enable verbose logging. **Crucial for debugging** provisioning scripts or connection issues. |
| `--plain` | Disable the TUI and use simple text output (ideal for CI/CD pipelines). |

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success. |
| `1` | General error (AWS API failure, Network issue). |
| `2` | Configuration error (`campers.yml` is invalid). |
| `130` | User interrupted (Ctrl+C). |

## Troubleshooting

### No Default VPC

```
No default VPC in us-east-1
```

**Fix:** Run `campers setup` to create a default VPC, or manually:

```bash
aws ec2 create-default-vpc --region us-east-1
```

### Invalid Instance Type

```
Invalid instance type
```

**Causes:**

- Instance type not available in this region
- Typo in instance type name

**Fix:** Check available instance types for your region or try a different region:

```bash
campers run dev --instance-type t3.medium
campers run dev --region us-west-2
```

### Insufficient IAM Permissions

```
Insufficient IAM permissions
```

**Required permissions:**

- Compute: `DescribeInstances`, `RunInstances`, `TerminateInstances`, `StartInstances`, `StopInstances`
- VPC: `DescribeVpcs`, `CreateDefaultVpc`
- Key Pairs: `CreateKeyPair`, `DeleteKeyPair`, `DescribeKeyPairs`
- Security Groups: `CreateSecurityGroup`, `AuthorizeSecurityGroupIngress`, `DescribeSecurityGroups`

### Instance Quota Exceeded

```
Instance quota exceeded
```

**Fix:** Request a quota increase in the AWS console:

[AWS Service Quotas Console](https://console.aws.amazon.com/servicequotas/)

Or terminate unused instances:

```bash
campers list --all
campers destroy <unused-instance>
```

### Expired Credentials

```
Cloud credentials have expired
```

**Fix:**

```bash
aws sso login           # If using AWS SSO
aws configure           # Re-configure credentials
```

### SSH Connectivity Issues

If you can't connect to your instance:

1. **Check instance state:** Is it running? Use `campers info <name>`.
2. **Check security group:** SSH port 22 must be open.
3. **Wait for startup:** New instances take 1-2 minutes to initialize.
4. **Network issues:** Try a different region or check your firewall.

**Debug with verbose mode:**

```bash
campers run dev -v
```