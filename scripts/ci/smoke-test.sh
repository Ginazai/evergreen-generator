#!/usr/bin/env bash
# Boots the freshly built image the way Render will run it and checks it answers.
# Catches what unit tests cannot: a broken Dockerfile/CMD, a missing runtime dependency
# in the slim image, a server bound to localhost instead of 0.0.0.0, ignoring $PORT.
#
#   IMAGE  default evergreen:ci
set -euo pipefail

IMAGE="${IMAGE:-evergreen:ci}"
NAME="evergreen-smoke-$$"
HOST_PORT=18501

cleanup() {
  status=$?
  if [[ "$status" -ne 0 ]]; then
    echo "::group::container logs (smoke test failed)"
    docker logs --tail 80 "$NAME" 2>&1 || true
    echo "::endgroup::"
  fi
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT

# Render injects PORT (10000 by default) and expects the service to listen on it.
docker run -d --name "$NAME" -e PORT=10000 -p "127.0.0.1:${HOST_PORT}:10000" "$IMAGE" >/dev/null

for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${HOST_PORT}/_stcore/health" >/dev/null 2>&1; then
    echo "✓ GUI healthy on \$PORT (try $i)"; break
  fi
  [[ "$i" -lt 30 ]] || { echo "✗ GUI never became healthy" >&2; exit 1; }
  sleep 2
done

curl -fsS "http://127.0.0.1:${HOST_PORT}/" >/dev/null && echo "✓ GUI serves /"
docker exec "$NAME" evergreen --help >/dev/null && echo "✓ evergreen CLI runs"
docker exec "$NAME" ffmpeg -version >/dev/null && echo "✓ ffmpeg present"
echo "All smoke checks passed."
