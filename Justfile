set dotenv-load := true


unit-test options="":
  uv run pytest {{options}}

bdd-test options="":
  uv run behave --summary {{options}}

test: unit-test bdd-test

test-fast: (unit-test "-x") (bdd-test "--stop")
