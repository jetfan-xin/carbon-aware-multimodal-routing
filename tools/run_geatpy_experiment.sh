#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output_dir=${1:-"$project_root/benchmarks/geatpy-23city-ablation"}
image_name="carbon-routing-geatpy:2.7.0"

mkdir -p "$output_dir"
docker build --platform linux/amd64 \
  --file "$project_root/Dockerfile.geatpy" \
  --tag "$image_name" \
  "$project_root"

docker run --rm --platform linux/amd64 \
  --user "$(id -u):$(id -g)" \
  --env MPLCONFIGDIR=/tmp/matplotlib \
  --volume "$project_root:/work:ro" \
  --volume "$output_dir:/output" \
  "$image_name" \
  python tools/run_geatpy_experiment.py --output-dir /output
