# Examples

Real-world configuration recipes for common use cases.

## Data Residency & PII Compliance

This pattern is essential for teams working with sensitive data (PII, PHI) that **cannot leave a specific geographic region**. By provisioning the workstation in the same region as the data, you ensure compliance because the data never touches your local laptop.

```yaml
vars:
  project: sensitive-analysis
  remote_dir: /home/ubuntu/${project}

defaults:
  # STRICTLY enforce the region where data resides
  region: eu-central-1  # Frankfurt (GDPR strict)
  
  # Filter out all environment variables to prevent accidental leakage
  # Only allow specific, safe variables
  env_filter:
    - ^SAFE_VAR_.*

camps:
  secure-workstation:
    instance_type: m5.2xlarge
    disk_size: 100
    
    command: |
      echo "Connected to secure workstation in eu-central-1."
      echo "Data analysis can proceed without downloading PII."
      bash
```

## Data Science (Jupyter + GPU)

A complete setup for deep learning. This camp spins up a GPU instance, installs PyTorch, and forwards Jupyter Lab to your local browser.

```yaml
vars:
  project: deep-learning
  remote_dir: /home/ubuntu/${project}

playbooks:
  gpu-setup:
    - name: Install Drivers
      hosts: all
      become: true
      tasks:
        - name: Install CUDA
          apt: {name: nvidia-cuda-toolkit, state: present}
        - name: Install PyTorch
          pip: {name: [torch, torchvision, jupyterlab, tensorboard]}

camps:
  experiment:
    instance_type: g5.xlarge  # NVIDIA A10G
    region: us-west-2
    disk_size: 200
    
    # Forward Jupyter (8888)
    ports: [8888]
    
    ansible_playbooks: [gpu-setup]
    
    # Auto-start Jupyter
    command: jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root

  training:
    instance_type: p3.2xlarge # V100 GPU
    region: us-west-2
    ports: [6006] # TensorBoard
    ansible_playbooks: [gpu-setup]
    
    # Pull data on every start
    startup_script: |
      cd ${remote_dir}
      dvc pull data/

    # Run background monitoring + training
    command: |
      tensorboard --logdir logs --port 6006 &
      python train_model.py
```

**Workflow:**
1. Run `campers run experiment` for interactive work.
2. Run `campers run training` for heavy batch jobs.

## Heavy Compilation (Rust/C++)

Offload long compile times to a high-core CPU instance.

```yaml
vars:
  project: rust-engine
  remote_dir: /home/ubuntu/${project}

camps:
  builder:
    instance_type: c6a.12xlarge  # 48 vCPUs!
    disk_size: 50
    
    setup_script: |
      curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
      sudo apt-get install -y build-essential clang
    
    command: cargo build --release
    
    # Auto-terminate after the build to save money
    on_exit: terminate
```

## Web Development (Full Control)

Run a backend, frontend, and database in the cloud using Docker Compose. This gives you full control over the environment.

```yaml
camps:
  webapp:
    instance_type: t3.medium
    
    # Forward Frontend, API, and DB admin ports
    ports:
      - 3000  # React
      - 8000  # FastAPI
      - 5432  # Postgres
    
    setup_script: |
      # Install Docker & Compose
      curl -fsSL https://get.docker.com | sh
      sudo usermod -aG docker ubuntu
      
    command: docker compose up
```

## Advanced: AWS Profile Support

If you rely on `AWS_PROFILE` (switching between accounts/roles) instead of raw environment variables, you can sync your credentials file to the remote instance.

!!! warning "Security Implication"
    This copies your **entire** `~/.aws` directory (all profiles) to the cloud instance.
    
    While Campers instances are secured by SSH keys and strictly limited security groups (no open ports), if the instance is compromised, all your local profiles are exposed. Only use this if you trust the environment.

```yaml
defaults:
  env_filter:
    # Forward the profile name env var
    - AWS_PROFILE

  sync_paths:
    # 1. Sync your code
    - local: .
      remote: /home/ubuntu/${project}
    
    # 2. Sync your AWS credentials
    - local: ~/.aws
      remote: /home/ubuntu/.aws
      ignore:
        - "cli/cache" # Don't sync CLI cache junk
```

**Usage:**
```bash
export AWS_PROFILE=dev-account
campers run
# On remote: aws s3 ls (uses dev-account profile)
```
