# Getting Started

This guide walks you through installing Campers and launching your first remote development environment.

## Prerequisites

Before using Campers, ensure you have:

- **Python 3.12+**
- **AWS credentials** configured via `aws configure` or environment variables
- **[Mutagen](https://mutagen.io/)** for file synchronization
- **[Ansible](https://docs.ansible.com/)** for playbook-based provisioning (optional)

### Installing Mutagen

=== "macOS"

    ```bash
    brew install mutagen-io/mutagen/mutagen
    ```

=== "Linux"

    ```bash
    curl -fsSL https://github.com/mutagen-io/mutagen/releases/latest/download/mutagen_linux_amd64_v0.18.1.tar.gz | tar xz
    sudo mv mutagen /usr/local/bin/
    ```

=== "Windows"

    ```powershell
    scoop install mutagen
    ```

### Configuring AWS Credentials

```bash
aws configure
```

Or set environment variables:

```bash
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_REGION=us-east-1
```

## Installation

### Using pip

```bash
pip install campers
```

### Using uv (recommended)

[uv](https://docs.astral.sh/uv/) lets you run Campers without installation:

```bash
uvx campers run
uvx campers list
```

Or install it in a project:

```bash
uv add campers
```

## Your First Camp

### 1. Generate Configuration

```bash
campers init
```

This creates a `campers.yaml` file with sensible defaults.

### 2. Review the Configuration

```yaml
defaults:
  region: us-east-1
  instance_type: t3.medium
  disk_size: 50

camps:
  dev:
    command: bash
```

### 3. Launch Your Camp

```bash
campers run dev
```

Campers will:

1. Create an EC2 instance in your AWS account
2. Generate and configure SSH keys
3. Start bidirectional file sync with Mutagen
4. Connect you to a shell on the remote instance

### 4. Work Remotely

Your local directory is now synced with the remote instance. Any changes you make locally appear on the remote, and vice versa.

### 5. Exit

Press `Ctrl+C` or type `exit`. By default, the instance stops (preserving your data). You can resume later with:

```bash
campers start dev
campers run dev
```

## Verifying Your Setup

Run the doctor command to check your AWS credentials and permissions:

```bash
campers doctor
```

This verifies:

- AWS credentials are configured
- Required IAM permissions are present
- Mutagen is installed (if file sync is enabled)

## Next Steps

- [Configuration](configuration.md) - Customize your camps
- [Commands](commands.md) - Explore all CLI options
- [Examples](examples.md) - Real-world configuration recipes
