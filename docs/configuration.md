# Configuration

Campers uses a YAML configuration file (`campers.yaml`) with four main sections: **variables**, **playbooks**, **defaults**, and **camps**.

## File Location

By default, Campers looks for `campers.yaml` in the current directory. Override with:

```bash
export CAMPERS_CONFIG=/path/to/config.yaml
```

## Structure Overview

```yaml
# 1. Variables (DRY configuration)
vars:
  project_name: my-app

# 2. Ansible Playbooks (Provisioning)
playbooks:
  base-setup: ...

# 3. Defaults (Global settings)
defaults:
  region: us-east-1

# 4. Camps (Machine definitions)
camps:
  dev: ...
  prod: ...
```

## Variables (`vars`)

Define reusable values that can be referenced anywhere using `${var_name}`. This is great for paths and project names.

```yaml
vars:
  project: my-ml-project
  remote_dir: /home/ubuntu/${project}
  python_version: "3.12"
```

Variables support:

- **Nested references**: `${remote_dir}/data` expands to `/home/ubuntu/my-ml-project/data`
- **Environment variables**: `${oc.env:HOME}` or `${oc.env:MY_VAR,default_value}`

## Playbooks (`playbooks`)

Ansible playbooks for provisioning instances. Define them once, reuse them across camps.

**Why Ansible?** It's idempotent. You can run it 100 times, and it only changes what's necessary.

```yaml
playbooks:
  # A simple playbook to install tools
  base:
    - name: Base system setup
      hosts: all
      become: true
      tasks:
        - name: Install packages
          apt: {name: [git, htop, tmux, curl], state: present}

  # A playbook for Python dev
  python-dev:
    - name: Python environment
      hosts: all
      tasks:
        - name: Install uv
          shell: curl -LsSf https://astral.sh/uv/install.sh | sh
          args:
            creates: ~/.local/bin/uv
```

## Defaults (`defaults`)

Base settings inherited by all camps. Useful for setting a common region or SSH user.

```yaml
defaults:
  region: us-east-1
  instance_type: t3.medium
  disk_size: 50
  ssh_username: ubuntu

  # Sync current directory to remote directory
  sync_paths:
    - local: .
      remote: /home/ubuntu/${project}

  # Don't sync these local files
  ignore:
    - "*.pyc"
    - __pycache__
    - .venv/
    - .git/
```

## Camps (`camps`)

Named configurations that override defaults. Each key under `camps` is a valid argument for `campers run <NAME>`.

```yaml
camps:
  # Simple dev machine
  dev:
    instance_type: t3.large
    command: bash

  # GPU machine for experiments
  experiment:
    instance_type: g5.xlarge
    ami:
      query:
        name: "Deep Learning Base AMI (Ubuntu*)*"
        owner: "amazon"
    ports: [8888]
    command: jupyter lab --ip=0.0.0.0 --port=8888
```

## Settings Reference

### AMI Selection (`ami`)

You can specify an exact AMI ID or a dynamic query to find the latest one.

**Option 1: Dynamic Query (Recommended)**
Finds the latest image matching the name pattern.
```yaml
ami:
  query:
    name: "Deep Learning Base AMI (Ubuntu*)*"
    owner: "amazon"
    architecture: "x86_64" # or arm64
```

**Option 2: Exact ID**
Pins the instance to a specific image.
```yaml
ami:
  image_id: ami-0123456789abcdef0
```

### Lifecycle Scripts

Campers has three distinct phases for running code:

1.  **Provisioning (`ansible_playbooks`)**:
    *   **When:** Runs on first boot (and on subsequent runs).
    *   **Purpose:** Installing system packages (apt, yum), drivers (CUDA), and global tools.
    *   **Tool:** Ansible.

2.  **One-time Setup (`setup_script`)**:
    *   **When:** Runs *only once* when the instance is first created.
    *   **Purpose:** Cloning repos, simple pip installs (if not using Ansible).
    *   **Tool:** Shell script.

3.  **Startup (`startup_script`)**:
    *   **When:** Runs *every time* you run `campers run`.
    *   **Purpose:** Fetching latest data (DVC), activating venvs, setting env vars.
    *   **Tool:** Shell script.

```yaml
camps:
  training:
    # 1. Install system deps
    ansible_playbooks: [python-setup]
    
    # 2. Pull latest data (every run)
    startup_script: |
      cd ${remote_dir}
      dvc pull data/
      source .venv/bin/activate
    
    # 3. Run the job
    command: python train.py
```

### Environment Forwarding (`env_filter`)

By default, Campers does **not** forward your local environment variables to the remote instance for security. You must explicitly allow them using regex patterns.

```yaml
defaults:
  env_filter:
    - ^AWS_.*       # Forward all AWS_ACCESS_KEY_...
    - ^HF_TOKEN$    # Forward specific token
    - ^WANDB_.*     # Forward Weights & Biases keys
```

### File Synchronization (`sync_paths`)

Campers uses **Mutagen** for high-performance, bi-directional sync.

| Setting | Description |
|---------|-------------|
| `sync_paths` | List of `local` and `remote` pairs. |
| `ignore` | List of file patterns to exclude (like `.git`, `node_modules`). |
| `include_vcs` | Boolean. Set to `true` to sync `.git` folder (default `false`). |

```yaml
sync_paths:
  - local: .
    remote: /home/ubuntu/project
```

### Port Forwarding (`ports`)

Automatically tunnels remote ports to `localhost`.

```yaml
ports:
  - 8888   # Jupyter
  - 6006   # TensorBoard
  - 5432   # PostgreSQL
```

### Lifecycle (`on_exit`)

Controls what happens when you exit the `campers run` session.

- `stop` (Default): Instance is stopped. Disk is preserved. You pay for storage.
- `terminate`: Instance is destroyed. Disk is deleted. You pay nothing.

```yaml
camps:
  # Build jobs should clean up after themselves
  builder:
    on_exit: terminate
```