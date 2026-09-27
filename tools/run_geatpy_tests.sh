#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
image_name="carbon-routing-geatpy:2.7.0"

docker build --platform linux/amd64 \
  --file "$project_root/Dockerfile.geatpy" \
  --tag "$image_name" \
  "$project_root"

docker run --rm --platform linux/amd64 \
  --volume "$project_root:/work:ro" \
  "$image_name"

docker run --rm --platform linux/amd64 \
  --volume "$project_root:/work:ro" \
  "$image_name" \
  python -m routing \
  examples/synthetic-network.json \
  --solver geatpy --population 20 --generations 12 --seed 42
