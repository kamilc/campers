"""Configuration template for campers setup."""

CONFIG_TEMPLATE = """# Campers Configuration File
# Location: campers.yaml (or set CAMPERS_CONFIG environment variable)
#
# Structure:
#   vars:      - Reusable variables (use ${var_name} to reference)
#   playbooks: - Ansible playbooks for provisioning (recommended)
#   defaults:  - Settings inherited by all camps
#   camps:     - Named configurations that override defaults

# ==============================================================================
# Variables - Define once, use everywhere with ${var_name}
# ==============================================================================
vars:
  project: my-project
  remote_dir: /home/ubuntu/${project}
  python_version: "3.12"

# ==============================================================================
# Ansible Playbooks - Recommended for provisioning (idempotent, declarative)
# ==============================================================================
# Define playbooks here, reference them in camps with:
#   ansible_playbook: playbook-name      (single)
#   ansible_playbooks: [play1, play2]    (multiple, run in order)

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

        - name: Install essential packages
          apt:
            name:
              - git
              - htop
              - tmux
              - curl
              - unzip
            state: present

  python-dev:
    - name: Python development environment
      hosts: all
      tasks:
        - name: Install uv package manager
          shell: curl -LsSf https://astral.sh/uv/install.sh | sh
          args:
            creates: ~/.local/bin/uv

        - name: Create project directory
          file:
            path: ${remote_dir}
            state: directory

  jupyter:
    - name: Jupyter Lab setup
      hosts: all
      tasks:
        - name: Verify uv is available for Jupyter
          shell: ~/.local/bin/uv --version

# ==============================================================================
# Defaults - Inherited by all camps
# ==============================================================================
defaults:
  region: us-east-1
  instance_type: t3.medium
  disk_size: 50

  sync_paths:
    - local: .
      remote: ${remote_dir}

  ports:
    - 8888

  include_vcs: false
  ignore:
    - "*.pyc"
    - __pycache__
    - "*.log"
    - .DS_Store
    - node_modules/
    - .venv/

  env_filter:
    - AWS_.*
    - HF_TOKEN
    - WANDB_API_KEY

# ==============================================================================
# Camps - Named configurations (override defaults as needed)
# ==============================================================================
camps:
  dev:
    instance_type: t3.large
    disk_size: 100
    ansible_playbooks:
      - base
      - python-dev
    command: cd ${remote_dir} && bash

  jupyter:
    instance_type: m5.xlarge
    disk_size: 200
    ports:
      - 8888
      - 6006
    ansible_playbooks:
      - base
      - python-dev
      - jupyter
    command: |
      ~/.local/bin/uv run --no-project \
        --with jupyter --with jupyterlab \
        --with pandas --with numpy --with matplotlib \
        jupyter lab --ip=0.0.0.0 --port=8888 --no-browser
    ignore:
      - "*.pyc"
      - __pycache__
      - .venv/
      - data/
      - models/
      - "*.parquet"

  gpu:
    instance_type: g5.xlarge
    disk_size: 200
    region: us-west-2
    ports:
      - 8888
      - 6006
    env_filter:
      - AWS_.*
      - HF_.*
      - WANDB_.*
      - CUDA_.*
    ansible_playbooks:
      - base
      - python-dev
      - jupyter
    command: |
      ~/.local/bin/uv run --no-project \
        --with jupyter --with jupyterlab \
        --with pandas --with numpy --with matplotlib \
        jupyter lab --ip=0.0.0.0 --port=8888 --no-browser

# ==============================================================================
# Alternative: Shell Scripts (simpler, but not idempotent)
# ==============================================================================
# Instead of Ansible playbooks, you can use shell scripts:
#
# camps:
#   simple-dev:
#     setup_script: |
#       sudo apt update
#       sudo apt install -y git htop
#       curl -LsSf https://astral.sh/uv/install.sh | sh
#     startup_script: |
#       cd ${remote_dir}
#       source .venv/bin/activate
#     command: bash
"""
