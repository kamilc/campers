# Campers

Campers is a command-line tool for managing remote development environments on AWS EC2. It handles the full lifecycle of cloud development machines: provisioning instances, synchronizing files, forwarding ports, and executing commands.

## Features

- **Instance Management**: Launch, stop, start, and destroy EC2 instances with a single command
- **File Synchronization**: Bidirectional sync between local and remote directories using Mutagen
- **Port Forwarding**: Automatic SSH tunnels for accessing remote services (Jupyter, databases, etc.)
- **Ansible Provisioning**: Declarative, idempotent instance setup with reusable playbooks
- **Environment Forwarding**: Securely forward local environment variables to remote instances
- **Named Configurations**: Define multiple "camps" for different workloads (dev, jupyter, gpu)
- **Variable Interpolation**: DRY configuration with reusable variables

## Installation

```bash
pip install campers
```

Alternatively, run directly without installation using [uv](https://docs.astral.sh/uv/):

```bash
uvx campers run
uvx campers list
```

### Prerequisites

- Python 3.12+
- AWS credentials configured (`aws configure` or environment variables)
- [Mutagen](https://mutagen.io/) for file synchronization
- [Ansible](https://docs.ansible.com/) for playbook-based provisioning (optional)

## Quick Start

```bash
# Generate a configuration file
campers init

# Launch an instance with defaults
campers run

# Launch a named camp
campers run jupyter

# List running instances
campers list

# Stop an instance (preserves data)
campers stop dev

# Destroy an instance
campers destroy dev
```

## Configuration

Campers uses a YAML configuration file (`campers.yaml`) with four main sections:

### Variables

Define reusable values that can be referenced anywhere using `${var_name}`:

```yaml
vars:
  project: my-ml-project
  remote_dir: /home/ubuntu/${project}
```

### Playbooks

Ansible playbooks for provisioning instances. Define once, reuse across camps:

```yaml
playbooks:
  base:
    - name: Base system setup
      hosts: all
      become: true
      tasks:
        - name: Install packages
          apt:
            name: [git, htop, tmux]
            state: present

  python-dev:
    - name: Python environment
      hosts: all
      tasks:
        - name: Install uv
          shell: curl -LsSf https://astral.sh/uv/install.sh | sh
          args:
            creates: ~/.local/bin/uv
```

### Defaults

Base settings inherited by all camps:

```yaml
defaults:
  region: us-east-1
  instance_type: t3.medium
  disk_size: 50

  ports:
    - 8888

  ignore:
    - "*.pyc"
    - __pycache__
    - .venv/

  env_filter:
    - AWS_.*
    - HF_TOKEN

  ansible_playbook: base
```

### Camps

Named configurations that override defaults:

```yaml
camps:
  dev:
    instance_type: t3.large
    ansible_playbooks: [base, python-dev]
    command: cd ${remote_dir} && bash

  jupyter:
    instance_type: m5.xlarge
    disk_size: 200
    ports: [8888, 6006]
    ansible_playbooks: [base, python-dev, jupyter]
    command: jupyter lab --ip=0.0.0.0 --port=8888 --no-browser

  gpu:
    instance_type: g5.xlarge
    region: us-west-2
    ansible_playbooks: [base, python-dev]
    env_filter:
      - AWS_.*
      - CUDA_.*
      - HF_.*
```

## Commands

### run

Launch an EC2 instance with file sync and command execution.

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

### list

Display all campers-managed instances across regions.

```bash
campers list

# Filter by region
campers list --region us-west-2
```

### stop

Stop a running instance. The instance and its data are preserved.

```bash
campers stop dev
campers stop i-0abc123def456
```

### start

Start a previously stopped instance.

```bash
campers start dev
campers start i-0abc123def456
```

### destroy

Terminate an instance and delete associated resources (key pair, security group).

```bash
campers destroy dev
campers destroy i-0abc123def456
```

### init

Generate a starter configuration file.

```bash
campers init

# Overwrite existing config
campers init --force
```

### doctor

Verify AWS credentials and required IAM permissions.

```bash
campers doctor
```

### setup

Create required AWS resources (VPC, security groups) for a region.

```bash
campers setup
campers setup --region eu-west-1
```

## Configuration Reference

### Instance Settings

| Setting | Type | Description |
|---------|------|-------------|
| `region` | string | AWS region (e.g., `us-east-1`) |
| `instance_type` | string | EC2 instance type (e.g., `t3.medium`, `g5.xlarge`) |
| `disk_size` | integer | Root volume size in GB |
| `ami` | object | AMI selection (see below) |

### File Synchronization

| Setting | Type | Description |
|---------|------|-------------|
| `sync_paths` | list | Local/remote directory pairs to sync |
| `include_vcs` | boolean | Include `.git` and other VCS files |
| `ignore` | list | File patterns to exclude from sync |

### Port Forwarding

| Setting | Type | Description |
|---------|------|-------------|
| `port` | integer | Single port to forward |
| `ports` | list | Multiple ports to forward |

### Environment

| Setting | Type | Description |
|---------|------|-------------|
| `env_filter` | list | Regex patterns matching env vars to forward |
| `command` | string | Default command to execute |

### Provisioning

| Setting | Type | Description |
|---------|------|-------------|
| `ansible_playbook` | string | Single playbook to run |
| `ansible_playbooks` | list | Multiple playbooks to run in order |
| `setup_script` | string | Shell script for initial setup |
| `startup_script` | string | Shell script to run before each command |

### Lifecycle

| Setting | Type | Description |
|---------|------|-------------|
| `on_exit` | string | Action when session ends: `stop` (default) or `terminate` |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CAMPERS_CONFIG` | Path to configuration file (default: `campers.yaml`) |
| `CAMPERS_DIR` | Data directory for keys (default: `~/.campers`) |
| `CAMPERS_DEBUG` | Enable debug logging (`1` to enable) |
| `AWS_PROFILE` | AWS credentials profile to use |
| `AWS_REGION` | Default AWS region |

## Examples

### Data Science Workflow

```yaml
vars:
  project: ml-experiments
  remote_dir: /home/ubuntu/${project}

playbooks:
  datascience:
    - name: Data science setup
      hosts: all
      tasks:
        - name: Install Python packages
          shell: |
            uv pip install --system \
              jupyter pandas numpy scikit-learn matplotlib seaborn

camps:
  notebook:
    instance_type: m5.xlarge
    disk_size: 100
    ports: [8888]
    ansible_playbooks: [base, datascience]
    command: jupyter lab --ip=0.0.0.0 --port=8888 --no-browser
    env_filter:
      - AWS_.*
```

### GPU Training

```yaml
camps:
  train:
    instance_type: p3.2xlarge
    region: us-west-2
    disk_size: 200
    ports: [6006]
    env_filter:
      - AWS_.*
      - WANDB_.*
      - HF_TOKEN
    command: cd ${remote_dir} && python train.py
    on_exit: terminate
```

### Web Development

```yaml
camps:
  webdev:
    instance_type: t3.medium
    ports: [3000, 5432, 6379]
    ignore:
      - node_modules/
      - .next/
      - "*.log"
    command: npm run dev
```

## License

MIT
