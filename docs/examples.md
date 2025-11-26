# Examples

Real-world configuration recipes for common use cases.

## Data Science Workflow

A complete setup for data science and machine learning work with Jupyter Lab.

```yaml
vars:
  project: ml-experiments
  remote_dir: /home/ubuntu/${project}

playbooks:
  datascience:
    - name: Data science setup
      hosts: all
      tasks:
        - name: Install uv
          shell: curl -LsSf https://astral.sh/uv/install.sh | sh
          args:
            creates: ~/.local/bin/uv

        - name: Install Python packages
          shell: |
            ~/.local/bin/uv pip install --system \
              jupyter pandas numpy scikit-learn \
              matplotlib seaborn plotly

defaults:
  region: us-east-1
  instance_type: t3.medium
  disk_size: 50
  ansible_playbooks: [datascience]
  env_filter:
    - AWS_.*

camps:
  notebook:
    instance_type: m5.xlarge
    disk_size: 100
    ports: [8888]
    command: jupyter lab --ip=0.0.0.0 --port=8888 --no-browser
```

**Usage:**

```bash
campers run notebook
# Open http://localhost:8888 in your browser
```

## GPU Training

Configuration for deep learning training on GPU instances.

```yaml
vars:
  project: deep-learning
  remote_dir: /home/ubuntu/${project}

playbooks:
  cuda:
    - name: CUDA setup
      hosts: all
      become: true
      tasks:
        - name: Install NVIDIA drivers
          apt:
            name: nvidia-driver-535
            state: present

        - name: Install CUDA toolkit
          apt:
            name: nvidia-cuda-toolkit
            state: present

  pytorch:
    - name: PyTorch setup
      hosts: all
      tasks:
        - name: Install PyTorch
          shell: |
            pip install torch torchvision torchaudio \
              --index-url https://download.pytorch.org/whl/cu121

camps:
  train:
    instance_type: g5.xlarge
    region: us-west-2
    disk_size: 200
    ports: [6006]
    ansible_playbooks: [cuda, pytorch]
    env_filter:
      - AWS_.*
      - WANDB_.*
      - HF_TOKEN
    command: cd ${remote_dir} && python train.py
    on_exit: terminate
```

**Usage:**

```bash
# Set your API keys
export WANDB_API_KEY=your_key
export HF_TOKEN=your_token

# Run training
campers run train

# TensorBoard available at http://localhost:6006
```

## Web Development

Full-stack web development with database and cache.

```yaml
vars:
  project: webapp
  remote_dir: /home/ubuntu/${project}

playbooks:
  webdev:
    - name: Web development setup
      hosts: all
      become: true
      tasks:
        - name: Install Node.js
          shell: |
            curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
            apt-get install -y nodejs

        - name: Install PostgreSQL
          apt:
            name: postgresql
            state: present

        - name: Install Redis
          apt:
            name: redis-server
            state: present

        - name: Start services
          systemd:
            name: "{{ item }}"
            state: started
            enabled: yes
          loop:
            - postgresql
            - redis-server

camps:
  webdev:
    instance_type: t3.medium
    ports:
      - 3000   # Next.js/React
      - 5432   # PostgreSQL
      - 6379   # Redis
    ansible_playbooks: [webdev]
    ignore:
      - node_modules/
      - .next/
      - "*.log"
    command: npm run dev
```

**Usage:**

```bash
campers run webdev
# Frontend at http://localhost:3000
# Database at localhost:5432
# Redis at localhost:6379
```

## Multi-Environment Setup

Different configurations for development, staging, and testing.

```yaml
vars:
  project: myapp
  remote_dir: /home/ubuntu/${project}

defaults:
  region: us-east-1
  env_filter:
    - AWS_.*

camps:
  dev:
    instance_type: t3.medium
    disk_size: 50
    command: bash

  staging:
    instance_type: t3.large
    disk_size: 100
    ports: [8080]
    env_filter:
      - AWS_.*
      - DATABASE_URL
      - REDIS_URL
    command: ./scripts/run-staging.sh

  test:
    instance_type: t3.small
    disk_size: 30
    on_exit: terminate
    command: pytest tests/ -v
```

**Usage:**

```bash
# Development work
campers run dev

# Staging environment
campers run staging

# Run tests (instance terminates after)
campers run test
```

## Persistent Database Server

A long-running database server that persists between sessions.

```yaml
vars:
  project: database-server

playbooks:
  postgres:
    - name: PostgreSQL setup
      hosts: all
      become: true
      tasks:
        - name: Install PostgreSQL
          apt:
            name: [postgresql, postgresql-contrib]
            state: present

        - name: Configure PostgreSQL
          lineinfile:
            path: /etc/postgresql/14/main/postgresql.conf
            regexp: "^#?listen_addresses"
            line: "listen_addresses = '*'"

        - name: Allow remote connections
          lineinfile:
            path: /etc/postgresql/14/main/pg_hba.conf
            line: "host all all 0.0.0.0/0 md5"

        - name: Restart PostgreSQL
          systemd:
            name: postgresql
            state: restarted

camps:
  postgres:
    instance_type: t3.medium
    disk_size: 100
    ports: [5432]
    ansible_playbooks: [postgres]
    on_exit: stop
    command: |
      echo "PostgreSQL running on localhost:5432"
      echo "Press Ctrl+C to disconnect (instance keeps running)"
      sleep infinity
```

**Usage:**

```bash
# Start the database server
campers run postgres

# Connect from your local machine
psql -h localhost -U postgres

# Later, stop the server
campers stop postgres
```

## Jupyter with Custom Kernels

Jupyter setup with multiple Python versions and R.

```yaml
vars:
  project: notebooks
  remote_dir: /home/ubuntu/${project}

playbooks:
  jupyter-multi:
    - name: Multi-kernel Jupyter
      hosts: all
      tasks:
        - name: Install Python versions
          shell: |
            uv python install 3.10 3.11 3.12

        - name: Install Jupyter
          shell: uv pip install --system jupyterlab ipykernel

        - name: Register Python 3.10 kernel
          shell: |
            uv run --python 3.10 python -m ipykernel install \
              --user --name py310 --display-name "Python 3.10"

        - name: Register Python 3.11 kernel
          shell: |
            uv run --python 3.11 python -m ipykernel install \
              --user --name py311 --display-name "Python 3.11"

        - name: Install R and IRkernel
          become: true
          shell: |
            apt-get install -y r-base
            R -e "install.packages('IRkernel', repos='https://cran.r-project.org')"
            R -e "IRkernel::installspec()"

camps:
  jupyter:
    instance_type: m5.large
    disk_size: 100
    ports: [8888]
    ansible_playbooks: [jupyter-multi]
    command: jupyter lab --ip=0.0.0.0 --port=8888 --no-browser
```

## Cost-Optimized Batch Processing

Run batch jobs on spot-like instances that terminate after completion.

```yaml
vars:
  project: batch-processor
  remote_dir: /home/ubuntu/${project}

camps:
  batch:
    instance_type: c5.2xlarge
    region: us-east-2
    disk_size: 50
    on_exit: terminate
    env_filter:
      - AWS_.*
      - S3_BUCKET
      - JOB_ID
    command: |
      cd ${remote_dir}
      python process_batch.py --job-id $JOB_ID
      aws s3 cp results/ s3://$S3_BUCKET/results/$JOB_ID/ --recursive
      echo "Batch complete, instance will terminate"
```

**Usage:**

```bash
export S3_BUCKET=my-results-bucket
export JOB_ID=job-$(date +%s)

campers run batch
# Instance automatically terminates when done
```
