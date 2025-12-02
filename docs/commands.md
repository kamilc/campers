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
| `--plain` | Disable the TUI and use simple text output. | **Critical for CI/CD.** Use this when running in GitHub Actions or scripts. |

## list

Show all instances managed by Campers across all regions.

```bash
campers list
```

**What it shows:**
- **Status:** Running, Stopped, or Terminated.
- **Cost:** Estimated monthly cost (Compute + Storage).
- **Region:** Where the instance lives.

Use `--json` for programmatic output (e.g., building custom dashboards).

## stop

Stops the instance but **preserves the disk**.

```bash
campers stop <NAME>
```

*   **Cost:** You stop paying for EC2 compute (hourly rate). You **continue paying** for EBS storage (~$0.08/GB/month).
*   **Use Case:** "I'm done for the day, but I want to resume exactly where I left off tomorrow."
*   **Behind the Scenes:** Calls AWS `StopInstances`. The IP address will change upon restart (unless Elastic IP is used, which Campers doesn't default to).

## start

Starts a previously stopped instance.

```bash
campers start <NAME>
```

*   **Use Case:** Resuming work on a stopped camp.
*   **Note:** You usually don't need to run this manually. `campers run` automatically starts stopped instances.

## destroy

Terminates the instance and **deletes the disk**.

```bash
campers destroy <NAME>
```

*   **Cost:** All billing stops immediately.
*   **Use Case:** "Task complete. I don't need this environment or its data anymore."
*   **Safety:** It asks for confirmation unless you pass `--force`.

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