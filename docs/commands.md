# Commands

Complete reference for all Campers CLI commands.

## run

The primary command. It provisions, syncs, and connects you to the camp.

```bash
campers run [CAMP_NAME] [OPTIONS]
```

**Behavior:**
1.  If the instance doesn't exist, it creates it.
2.  If it's stopped, it starts it.
3.  It establishes the Mutagen file sync.
4.  It sets up SSH port forwarding.
5.  It opens an interactive SSH shell (or runs the specified command).

### TUI (Terminal User Interface)
By default, `run` opens a dashboard showing:
- **Sync Status:** Number of files synced.
- **Logs:** Output from startup scripts and commands.
- **Instance Stats:** IP address, region, uptime.

### Options

| Option | Description |
|--------|-------------|
| `-c`, `--command` | Command to execute instead of opening a shell |
| `--instance-type` | Override EC2 instance type (e.g., `c6a.xlarge`) |
| `--disk-size` | Override root volume size (GB) |
| `--region` | Override AWS region |
| `--port` | Additional port(s) to forward |
| `--plain` | Disable the TUI (useful for CI/CD or simple logs) |

## list

Show all instances managed by Campers.

```bash
campers list
```

Use `--json` for programmatic output (e.g., building custom dashboards).

## stop

Stops the instance but **preserves the disk**.

```bash
campers stop <NAME>
```

*   **Cost:** You stop paying for EC2 compute. You continue paying for EBS storage.
*   **Use Case:** End of the day. You want to resume exactly where you left off tomorrow.

## destroy

Terminates the instance and **deletes the disk**.

```bash
campers destroy <NAME>
```

*   **Cost:** All billing stops.
*   **Use Case:** Task complete. You don't need this environment anymore.

## init

Creates a `campers.yaml` starter file in the current directory.

```bash
campers init
```

## doctor

Diagnose common issues (AWS credentials, IAM permissions, Mutagen installation).

```bash
campers doctor
```

## setup

One-time setup helper. Creates a default VPC and Security Group in the specified region if they don't exist.

```bash
campers setup --region us-east-1
```

## Global Options

These options apply to most commands (especially `run`).

| Option | Description |
|--------|-------------|
| `-v`, `--verbose` | Enable verbose logging (useful for debugging provisioning scripts). |
| `--plain` | Disable the TUI and use simple text output (ideal for CI/CD pipelines). |

## Exit Codes