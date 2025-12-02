# Getting Started

This guide will help you spin up your first Campers environment in under 5 minutes.

## Prerequisites

1.  **AWS Credentials**: You need a valid AWS account.
    ```bash
    aws configure
    # Or export AWS_PROFILE=my-profile
    ```
2.  **Mutagen**: Required for the high-performance file sync.
    *   **macOS**: `brew install mutagen-io/mutagen/mutagen`
    *   **Linux**: [Download binary](https://mutagen.io/download)
    *   **Windows**: `scoop install mutagen`

## Installation

We recommend using **[uv](https://docs.astral.sh/uv/)** for a zero-install experience, but standard pip works too.

=== "Using uv (Recommended)"

    No installation required! just run:
    ```bash
    uvx campers run
    ```

=== "Using pip"

    ```bash
    pip install campers
    ```

## Your First Camp

### 1. Initialize

Go to a project folder (or create a dummy one) and run:

```bash
campers init
```

This creates a `campers.yaml` file. This file is your **Infrastructure as Code**. It defines the machine you need.

### 2. Configure (Optional)

Open `campers.yaml`. By default, it uses a small `t3.medium`. Let's say you want more power:

```yaml
defaults:
  region: us-east-1
  instance_type: t3.xlarge  # Upgrade to 4 vCPUs, 16GB RAM
  disk_size: 50
```

### 3. Run

```bash
campers run
```

**What happens next?**

1.  **Provisioning:** Campers asks AWS for the instance.
2.  **Sync:** It establishes the Mutagen session.
3.  **Shell:** You are dropped into an SSH shell on the remote machine.

### 4. The "Localhost" Experience

While inside the `campers run` session:

1.  **Edit Locally:** Open a file in your local VS Code. Save it.
2.  **Check Remotely:** Run `cat filename` in the remote shell. The change is already there.
3.  **Web Apps:** If you run a web server (e.g., `python -m http.server 8000`) on the remote machine, Campers automatically forwards the port. Open `http://localhost:8000` on your laptop.

### 5. Stop or Destroy

When you are done, you have two choices:

*   **Stop** (Ctrl+C or `campers stop`): Shuts down the instance. Data is preserved. You pay only for EBS storage (~$0.05/GB/month).
*   **Destroy** (`campers destroy`): Terminates the instance and deletes the disk. Costs stop completely.

## Optional: VS Code Remote SSH

Campers is designed to let you **edit locally** while Mutagen syncs changes instantly. This gives you the fastest possible typing latency.

However, if you prefer to use **VS Code Remote - SSH** (e.g., for the integrated terminal, remote debugging, or extensions that need to run on the host), you can still do so:

1.  Run `campers info` to get the IP address and key path.
2.  In VS Code, open the **Remote Explorer**.
3.  Add a new SSH Host:
    ```bash
    ssh -i /path/to/key.pem ubuntu@<INSTANCE_IP>
    ```
4.  Connect! You can now use the remote terminal and debugger directly.

## Next Steps

- Check out [Examples](examples.md) for Data Science and Web Dev setups.
- Learn about [Configuration](configuration.md) variables and playbooks.
