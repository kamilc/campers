set dotenv-load := true


unit-test options="":
  uv run pytest {{options}}

bdd-test options="":
  just build-ssh-image
  uv run behave --summary --stop {{options}}

test: unit-test bdd-test

test-fast: (unit-test "-x") (bdd-test "--stop")

localstack-start:
  docker rm -f moondock-localstack 2>/dev/null || true
  docker run -d --rm --name moondock-localstack -p 4566:4566 -p 4510-4559:4510-4559 -v /var/run/docker.sock:/var/run/docker.sock localstack/localstack:latest

localstack-stop:
  docker stop moondock-localstack

localstack-restart: localstack-stop localstack-start

localstack-health:
  curl -s http://localhost:4566/_localstack/health | python3 -m json.tool

build-ssh-image:
  docker build -t moondock/python-ssh:latest docker/python-ssh
