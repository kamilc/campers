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

### Variable Interpolation

Reference other variables using `${var_name}` syntax. Variables are resolved recursively, so you can build complex paths from simple components:

```yaml
vars:
  user: ubuntu
  project: my-app
  base_dir: /home/${user}
  remote_dir: ${base_dir}/${project}
  data_dir: ${remote_dir}/data
  logs_dir: ${remote_dir}/logs
```

With this configuration:

- `${remote_dir}` resolves to `/home/ubuntu/my-app`
- `${data_dir}` resolves to `/home/ubuntu/my-app/data`

### Environment Variables

Access your local environment variables using `${oc.env:VAR_NAME}`:

```yaml
vars:
  home: ${oc.env:HOME}
  user: ${oc.env:USER}
  project_root: ${oc.env:HOME}/projects/${project}
```

**With default values:** If an environment variable might not be set, provide a fallback:

```yaml
vars:
  api_endpoint: ${oc.env:API_URL,https://api.example.com}
  log_level: ${oc.env:LOG_LEVEL,INFO}
  cache_dir: ${oc.env:XDG_CACHE_HOME,~/.cache}/campers
```

The value after the comma is used when the environment variable is not set.

### Using `.env` Files

Campers automatically loads a `.env` file from the same directory as your `campers.yaml` if one exists. This is useful for storing secrets and environment-specific values outside of version control.

**Example `.env` file:**
```bash
# .env (add to .gitignore!)
DB_PASSWORD=mysecretpassword
API_KEY=sk-1234567890
AWS_REGION=us-west-2
```

**Reference in `campers.yaml`:**
```yaml
vars:
  db_password: ${oc.env:DB_PASSWORD}
  api_key: ${oc.env:API_KEY}
  region: ${oc.env:AWS_REGION,us-east-1}

defaults:
  region: ${region}
  env_filter:
    - ^DB_PASSWORD$
    - ^API_KEY$
```

**Important notes:**

- `.env` is loaded before config parsing, so all variables are available via `${oc.env:VAR}`
- Existing environment variables are NOT overwritten (shell takes precedence)
- Add `.env` to your `.gitignore` to avoid committing secrets

### Common Patterns

**Project-relative paths:**
```yaml
vars:
  project: my-ml-project
  remote_dir: /home/ubuntu/${project}

camps:
  dev:
    command: cd ${remote_dir} && bash
    startup_script: |
      cd ${remote_dir}
      source .venv/bin/activate
```

**Environment-aware configuration:**
```yaml
vars:
  env: ${oc.env:CAMPERS_ENV,development}
  region: ${oc.env:AWS_REGION,us-east-1}

defaults:
  region: ${region}
```

**Combining variables and environment:**
```yaml
vars:
  workspace: ${oc.env:HOME}/projects/${project}
  data_bucket: ${oc.env:DATA_BUCKET,my-default-bucket}

camps:
  training:
    startup_script: |
      aws s3 sync s3://${data_bucket}/data ${workspace}/data
```

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

### SSH Configuration (`ssh_username`)

By default, Campers assumes an Ubuntu AMI (`ssh_username: ubuntu`). If you use Amazon Linux or another distro, you must set the correct user.

```yaml
camps:
  amazon-linux:
    ssh_username: ec2-user
    ami:
      query: {name: "al2023-ami-*", owner: "amazon"}
```

**Username restrictions:**

- Must start with a lowercase letter or underscore
- Can contain: lowercase letters, numbers, underscores, hyphens
- Maximum 32 characters
- Common valid values: `ubuntu`, `ec2-user`, `admin`, `centos`

### Network Security (`ssh_allowed_cidr`)

By default, Campers opens SSH (port 22) to the world (`0.0.0.0/0`). You can restrict this to a specific IP range for better security.

```yaml
defaults:
  # Only allow SSH from my corporate VPN
  ssh_allowed_cidr: "203.0.113.0/24"
```

### Lifecycle Scripts

Campers has three distinct phases for running code:

1.  **Provisioning (`ansible_playbooks` or `ansible_playbook`)**:
    *   **When:** Runs on first boot (and on subsequent runs).
    *   **Purpose:** Installing system packages (apt, yum), drivers (CUDA), and global tools.
    *   **Tool:** Ansible.
    *   **Note:** Use `ansible_playbooks: [name1, name2]` for multiple playbooks, or `ansible_playbook: name` for a single playbook. These are mutually exclusive.

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

**Default ignore patterns:** These are always excluded unless you override them:

- `*.pyc`
- `__pycache__`
- `*.log`
- `.DS_Store`

**Per-path ignore patterns:** You can specify custom ignore patterns for individual sync paths:

```yaml
sync_paths:
  - local: .
    remote: /home/ubuntu/project
  - local: ~/.aws
    remote: /home/ubuntu/.aws
    ignore:
      - "cli/cache"
```

### Port Forwarding (`ports`)

Automatically tunnels remote ports to `localhost` via SSH. This is ideal for development - services appear on your local machine.

```yaml
ports:
  - 8888   # Jupyter → localhost:8888
  - 6006   # TensorBoard → localhost:6006
  - 5432   # PostgreSQL → localhost:5432
```

**Port mapping syntax:** Use `"remote:local"` to map to a different local port:

```yaml
ports:
  - 8888           # Same port: remote:8888 → local:8888
  - "8080:80"      # Different ports: remote:8080 → local:80
  - "6006:6007"    # Remote 6006 to local 6007
```

**Valid port range:** 1-65535. Ports below 1024 may require elevated privileges.

### Public Ports (`public_ports`)

Opens ports directly on the instance's public IP for external access. This is ideal for **client demos** where others need to access your running application.

```yaml
camps:
  demo:
    instance_type: t3.medium
    public_ports: [80, 443, 3000]
    command: npm start
```

With this configuration, clients can access your app at `http://<public-ip>:3000`.

**Security Note:** By default, public ports are open to the internet (`0.0.0.0/0`). You can restrict access to specific IP ranges:

```yaml
defaults:
  public_ports_allowed_cidr: "203.0.113.0/24"  # Only your office IP
```

| Setting | Purpose |
|---------|---------|
| `ports` | SSH tunneling to localhost (developer access) |
| `public_ports` | Security group rules (external/client access) |

### Session Exit

When you exit a `campers run` session (Q or Ctrl+C), you'll be prompted to choose:

- **Stop** (default): Instance is stopped. Disk is preserved. You pay for storage only.
- **Keep running**: Disconnect locally but keep the instance running. Useful for demos where clients still need access.
- **Destroy**: Terminate the instance and delete all data. You pay nothing.

This interactive prompt replaces the need for pre-configured exit behavior.

## Environment Variables

Campers respects several environment variables for configuration and debugging.

### Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CAMPERS_CONFIG` | Path to config file | `campers.yaml` |
| `CAMPERS_DIR` | Directory for keys and state | `~/.campers` |
| `CAMPERS_DEBUG` | Enable debug mode (shows stack traces) | `0` |

### SSH

| Variable | Description | Default |
|----------|-------------|---------|
| `CAMPERS_SSH_TIMEOUT` | SSH operation timeout in seconds | `30` |
| `CAMPERS_STRICT_HOST_KEY` | Enforce strict host key checking | `0` |

### Feature Toggles

| Variable | Description | Default |
|----------|-------------|---------|
| `CAMPERS_DISABLE_MUTAGEN` | Disable file sync entirely | `0` |

**Example usage:**

```bash
CAMPERS_DEBUG=1 campers run dev
CAMPERS_CONFIG=~/configs/work.yaml campers list
```

## Multi-User Support

When multiple developers share an AWS account, Campers automatically isolates instances by user.

### How It Works

1. **Owner tagging:** Each instance is tagged with an `Owner` tag containing your identity.
2. **Identity detection:** Campers uses your git email (`git config user.email`), falling back to `$USER` if not set.
3. **Filtered listing:** `campers list` shows only your instances by default.

### Commands

```bash
campers list          # Shows only your instances
campers list --all    # Shows all instances with Owner column
```

### Legacy Instances

Instances created before multi-user support (without an `Owner` tag):

- Do NOT appear in default `campers list` output
- Appear when using `--all` flag with owner shown as "unknown"

## Instance Naming

Campers automatically generates instance names based on your project context.

### Naming Strategy

```
campers-{project}-{branch}-{camp_name}
```

**Example:** `campers-myapp-feature-login-dev`

### Auto-Detection

Campers automatically detects:

- **Project name:** From git remote URL (e.g., `github.com/user/myapp` → `myapp`)
- **Branch name:** Current git branch (e.g., `feature/login` → `feature-login`)
- **Camp name:** From your command (e.g., `campers run dev` → `dev`)

**Fallback:** If not in a git repository, uses the current directory name.

### Name Truncation

Names are automatically truncated to fit AWS tag limits (256 characters).