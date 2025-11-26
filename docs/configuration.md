# Configuration

Campers uses a YAML configuration file (`campers.yaml`) with four main sections: **variables**, **playbooks**, **defaults**, and **camps**.

## File Location

By default, Campers looks for `campers.yaml` in the current directory. Override with:

```bash
export CAMPERS_CONFIG=/path/to/config.yaml
```

## Structure Overview

```yaml
vars:
  # Reusable variables

playbooks:
  # Ansible playbooks for provisioning

defaults:
  # Base settings for all camps

camps:
  # Named configurations
```

## Variables

Define reusable values that can be referenced anywhere using `${var_name}`:

```yaml
vars:
  project: my-ml-project
  remote_dir: /home/ubuntu/${project}
  python_version: "3.12"
```

Variables support:

- **Nested references**: `${remote_dir}/data` expands to `/home/ubuntu/my-ml-project/data`
- **Environment variables**: `${oc.env:HOME}` or `${oc.env:MY_VAR,default_value}`

## Playbooks

Ansible playbooks for provisioning instances. Define once, reuse across camps:

```yaml
playbooks:
  base:
    - name: Base system setup
      hosts: all
      become: true
      tasks:
        - name: Update apt cache
          apt:
            update_cache: yes
            cache_valid_time: 3600

        - name: Install packages
          apt:
            name: [git, htop, tmux, curl]
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

## Defaults

Base settings inherited by all camps:

```yaml
defaults:
  region: us-east-1
  instance_type: t3.medium
  disk_size: 50
  ssh_username: ubuntu

  sync_paths:
    - local: .
      remote: /home/ubuntu/${project}

  ports:
    - 8888

  ignore:
    - "*.pyc"
    - __pycache__
    - .venv/
    - .git/

  env_filter:
    - AWS_.*
    - HF_TOKEN

  ansible_playbook: base
  on_exit: stop
```

## Camps

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
    ansible_playbooks: [base, python-dev]
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

## Settings Reference

### Instance Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `region` | string | `us-east-1` | AWS region |
| `instance_type` | string | `t3.medium` | EC2 instance type |
| `disk_size` | integer | `50` | Root volume size in GB |
| `ssh_username` | string | `ubuntu` | SSH username for connection |
| `ami` | object | — | AMI selection (see below) |

### AMI Selection

```yaml
ami:
  name: "ubuntu/images/hvm-ssd/ubuntu-*-24.04-amd64-server-*"
  owner: "099720109477"  # Canonical
```

### File Synchronization

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `sync_paths` | list | — | Local/remote directory pairs |
| `include_vcs` | boolean | `false` | Include `.git` directories |
| `ignore` | list | `[]` | File patterns to exclude |

```yaml
sync_paths:
  - local: .
    remote: /home/ubuntu/project
  - local: ~/data
    remote: /home/ubuntu/data
```

### Port Forwarding

| Setting | Type | Description |
|---------|------|-------------|
| `port` | integer | Single port to forward |
| `ports` | list | Multiple ports to forward |

```yaml
ports:
  - 8888   # Jupyter
  - 6006   # TensorBoard
  - 5432   # PostgreSQL
```

Ports are forwarded from `localhost:<port>` to the remote instance.

### Environment Variables

| Setting | Type | Description |
|---------|------|-------------|
| `env_filter` | list | Regex patterns matching env vars to forward |

```yaml
env_filter:
  - AWS_.*       # All AWS credentials
  - HF_TOKEN     # Hugging Face token
  - WANDB_.*     # Weights & Biases
  - ^DB_.*       # Database credentials
```

!!! warning "Security Note"
    Be careful with environment forwarding. Campers warns when forwarding variables containing `SECRET`, `PASSWORD`, `TOKEN`, or `KEY`.

### Commands and Scripts

| Setting | Type | Description |
|---------|------|-------------|
| `command` | string | Command to execute after setup |
| `setup_script` | string | One-time setup script (runs once per instance) |
| `startup_script` | string | Script to run before each command |

```yaml
setup_script: |
  pip install -r requirements.txt

startup_script: |
  source ~/.bashrc
  cd ${remote_dir}

command: python train.py
```

### Provisioning

| Setting | Type | Description |
|---------|------|-------------|
| `ansible_playbook` | string | Single playbook name |
| `ansible_playbooks` | list | Multiple playbooks (run in order) |

```yaml
ansible_playbooks:
  - base
  - python-dev
  - jupyter
```

### Lifecycle

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `on_exit` | string | `stop` | Action when session ends: `stop` or `terminate` |

- `stop`: Instance stops, data preserved, can be restarted
- `terminate`: Instance and data destroyed

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CAMPERS_CONFIG` | Path to configuration file |
| `CAMPERS_DIR` | Data directory for keys (default: `~/.campers`) |
| `CAMPERS_DEBUG` | Enable debug logging (`1` to enable) |
| `AWS_PROFILE` | AWS credentials profile |
| `AWS_REGION` | Default AWS region |

## Configuration Merging

Settings are merged in this order (later overrides earlier):

1. Built-in defaults
2. `defaults:` section in config
3. Camp-specific settings
4. CLI arguments

```bash
# CLI arguments override everything
campers run dev --instance-type t3.xlarge --disk-size 100
```
