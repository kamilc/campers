# Campers

<p align="center">
  <img src="docs/assets/campers.png" alt="Campers" width="400">
</p>

<h3 align="center">
  Local development experience. Remote cloud resources.
</h3>

Campers is a command-line tool that manages disposable remote development environments on the cloud (currently AWS EC2). It allows you to offload heavy computation to the cloud while keeping your local development workflow intact.

It bridges the gap between your local machine and a cloud instance by handling provisioning, file synchronization, and network tunneling automatically.

## How you use it

The goal of Campers is to make a remote cloud instance feel like localhost.

Imagine you are working on a resource-intensive project, like a large microservices stack or a deep learning model. Your local machine is struggling with heat and memory limits.

With Campers, the workflow looks like this:

1.  **Configuration**: You add a `campers.yml` file to your project root. This defines the hardware you need (e.g., an instance type like `p3.2xlarge`), the setup steps, and which ports to forward.

2.  **Spin Up**: You run `campers run` in your terminal.
    In the background, Campers provisions the instance, configures it (via shell scripts or Ansible), and establishes a real-time, two-way file sync using Mutagen.

3.  **Development**: You stay on your laptop.
    *   You edit code in your local editor (VS Code, Vim, etc.). Changes are synced instantly to the cloud instance.
    *   You run your application on the remote instance.
    *   You access the application via `localhost` in your browser. Campers tunnels the traffic through SSH automatically.

4.  **Exit Options**:
    When you press Q or Ctrl+C, you'll be prompted to choose:
    *   **Stop** (default): Instance is stopped but preserved. Resume later with `campers run`.
    *   **Keep running**: Disconnect locally but keep the instance running. Ideal for demos where clients need continued access.
    *   **Destroy**: Terminate and delete everything. You can also run `campers destroy` anytime.

<p align="center">
  <img src="docs/assets/infographic.jpg" alt="Campers Workflow Infographic" width="100%">
</p>

## Use Cases

**Data Science & Pipelines**
Ideal for ad-hoc data science projects. Run resource-intensive data pipelines or train models on high-end cloud hardware.

It also solves **data residency** challenges. Many organizations strictly prohibit storing PII on developer laptops. By spinning up a camp in a compliant cloud region, you can develop against real datasets without ever downloading sensitive data to your local machine.

**Isolated Environments**
Instead of cluttering your local machine with databases and system dependencies, you can define a clean, reproducible environment for each project. If the environment breaks, you simply destroy it and create a new one.

**Heavy Compilation**
If you are compiling large C++ or Rust projects, you can provision a high-core instance (like a `c6a.24xlarge`) for the duration of the build. You get the build speed of a workstation without maintaining the hardware.

**Client Demos**
Share running applications with clients by exposing ports publicly. Use `public_ports` to open security group rules, then select "Keep running" on exit so clients can continue accessing your demo while you disconnect.

## Features

- **Mutagen Sync**: Uses [Mutagen](https://mutagen.io/) for high-performance file synchronization. It is not `rsync`; it uses a real-time, bi-directional sync agent that is orders of magnitude faster for large projects (like `node_modules`).
- **Automatic Port Forwarding**: Tunnels remote ports to your local machine based on your configuration.
- **Public Port Exposure**: Open ports directly for external access - perfect for client demos.
- **Ansible Integration**: Supports running Ansible playbooks to configure the instance on startup.
- **Multi-User Support**: Teams sharing an AWS account get automatic instance isolation. Each instance is tagged with the owner's identity, and `campers list` shows only your instances by default.
- **Docker-like Exec**: Run commands on running instances with `campers exec dev "command" -it` - no re-sync or re-provision needed.
- **Cost Control:** Encourages an ephemeral workflow where instances are destroyed when not in use.
- **TUI Dashboard**: A terminal interface to monitor logs, sync status, and instance health.

## Simple Configuration

Campers uses a single YAML file to define your infrastructure and provisioning. Here is a complete example:

```yaml
# campers.yml

# Define reusable variables to keep config clean
vars:
  project_name: my-ml-project
  # Use standard linux paths
  remote_path: /home/ubuntu/${project_name}

# Define reusable Ansible playbooks (idempotent setup)
playbooks:
  python-setup:
    - name: Install Python Tools
      hosts: all
      tasks:
        - pip: {name: [numpy, pandas, jupyter], state: present}

  deep-learning:
    - name: Install PyTorch & TensorBoard
      hosts: all
      tasks:
        - pip: {name: [torch, torchvision, tensorboard], state: present}

# Define your camps (machines)
camps:
  # 1. Cheap dev environment
  dev:
    instance_type: t3.medium
    # Uses variable defined above
    command: cd ${remote_path} && bash

  # 2. Interactive experimentation (Jupyter)
  experiment:
    instance_type: g4dn.xlarge
    # Use the Deep Learning AMI
    ami:
      query:
        name: "Deep Learning Base AMI (Ubuntu*)*"
        owner: "amazon"
    # Open Jupyter on your laptop's localhost:8888
    ports: [8888]
    ansible_playbooks: [python-setup]
    command: jupyter lab --ip=0.0.0.0 --port=8888

  # 3. Heavy training job (TensorBoard)
  training:
    instance_type: p3.2xlarge
    # Forward TensorBoard to localhost:6006
    ports: [6006]
    ansible_playbooks: [python-setup, deep-learning]

    # Run every time the instance starts (e.g., pull latest data)
    startup_script: |
      cd ${remote_path}
      dvc pull data/

    # Run background monitoring and main training script
    command: |
      cd ${remote_path}
      tensorboard --logdir logs --port 6006 &
      python train_model.py

  # 4. Client demo (publicly accessible)
  demo:
    instance_type: t3.medium
    # Open ports for external access (clients can hit the public IP)
    public_ports: [80, 3000]
    command: npm start
```

**How you use them:**

```bash
# Start the cheap coding environment
campers run dev

# Switch to the GPU machine for notebooks
campers run experiment

# Launch the heavy training job
campers run training

# Start a client demo (share the public IP with clients)
campers run demo

# Open another shell to a running camp (like docker exec)
campers exec dev "/bin/bash" -it

# Run a one-off command without interrupting your session
campers exec dev "tail -f /var/log/app.log"

# Check status of all your camps (showing estimated monthly costs)
campers list
# ┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
# ┃ NAME               ┃ INSTANCE-ID  ┃ STATUS     ┃ REGION         ┃ COST/MONTH           ┃
# ┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
# │ campers-dev        │ i-0abc123def │ running    │ us-east-1      │ $29.95/month         │
# │ campers-experiment │ i-0def456abc │ stopped    │ us-east-1      │ $4.00/month          │
# └────────────────────┴──────────────┴────────────┴────────────────┴──────────────────────┘
```

### Full Control
Since you get a standard Linux instance, you can run **multiple services** at once. You might use `supervisord` or `docker compose` to spin up Jupyter, TensorBoard, and a database simultaneously. Campers will automatically forward all the ports you specify.

### Environment Forwarding
Campers securely forwards your local environment variables (like API keys) to the remote instance. You can configure exactly which variables to send using regex filters:

```yaml
defaults:
  # Only forward specific safe variables
  env_filter:
    - ^AWS_.*
    - ^WANDB_API_KEY
```

### `.env` File Support
Campers automatically loads a `.env` file from your project directory. Use it to store secrets outside of version control:

```bash
# .env (add to .gitignore!)
DB_PASSWORD=secret
API_KEY=sk-123
```

Reference them in `campers.yaml` with `${oc.env:VAR_NAME}`:

```yaml
vars:
  api_key: ${oc.env:API_KEY}
  db_pass: ${oc.env:DB_PASSWORD,default_value}
```

## Quick Start

```bash
# Install via pip
pip install campers

# Or run instantly with uv (recommended)
uvx campers run

# Check prerequisites (AWS credentials, Mutagen, etc.)
campers doctor

# First-time setup (creates default VPC if needed)
campers setup

# Initialize a configuration in your current directory
campers init

# Validate your configuration
campers validate

# Spin up your camp
campers run
```

## Setup & Troubleshooting

### First-Time Setup

If you're using a new AWS account or region, run the setup command to ensure prerequisites are in place:

```bash
campers setup --region us-east-1
```

This creates a default VPC (required for launching instances) and verifies IAM permissions.

### Diagnosing Issues

If something isn't working, run the doctor command:

```bash
campers doctor
```

It checks:
- AWS credentials and connectivity
- IAM permissions
- Default VPC availability
- Mutagen installation

For verbose output with stack traces, enable debug mode:

```bash
CAMPERS_DEBUG=1 campers run dev
```

## Documentation

Full documentation is available at **[kamilc.github.io/campers](https://kamilc.github.io/campers)**

- [Getting Started](https://kamilc.github.io/campers/getting-started/)
- [Configuration Reference](https://kamilc.github.io/campers/configuration/)
- [CLI Commands](https://kamilc.github.io/campers/commands/)
- [Examples](https://kamilc.github.io/campers/examples/)

## License

MIT
