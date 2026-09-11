#!/usr/bin/env bash
# Usage:
#   build-container/build.sh image   - build the container image (installs packages inside the image only)
#   build-container/build.sh deps    - build third party dependencies into deps/build (1-2 h first time)
#   build-container/build.sh slicer  - configure and build PrusaSlicer into build/
#   build-container/build.sh shell   - interactive shell in the container
#   build-container/build.sh run     - start the built PrusaSlicer on the host with build/datadir-dev as data dir
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="localhost/prusaslicer-build:fedora43"
JOBS="${JOBS:-$(nproc)}"

run() {
    podman run --rm -it --userns=keep-id -v "$REPO:/src:Z" -w /src -e JOBS="$JOBS" -e LANG=C.UTF-8 -e LC_ALL=C.UTF-8 -e HOME=/tmp "$IMAGE" "$@"
}

case "${1:-}" in
    image)
        podman build -t "$IMAGE" -f "$REPO/build-container/Containerfile" "$REPO/build-container"
        ;;
    deps)
        run bash -c 'mkdir -p deps/build && cd deps/build && cmake -G Ninja .. && cmake --build . -j "$JOBS"'
        ;;
    slicer)
        run bash -c 'mkdir -p build && cd build && cmake -G Ninja .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="/src/deps/build/destdir/usr/local" && cmake --build . -j "$JOBS"'
        # the build creates build/src/resources -> /src/resources, which only resolves inside the container
        ln -sfn ../../resources "$REPO/build/src/resources"
        ;;
    run)
        # run the built launcher on the host with a private data directory
        mkdir -p "$REPO/build/datadir-dev/lua"
        exec "$REPO/build/src/slic3r-app-launcher/slic3r-app-launcher" --datadir "$REPO/build/datadir-dev" "${@:2}"
        ;;
    shell)
        run bash
        ;;
    *)
        sed -n '2,8p' "$0"; exit 1
        ;;
esac
