#!/usr/bin/env bash
# Unpack runtime-data.tar.gz on the server (step 6 of deploy/AZURE_DEPLOYMENT.md).
#   sudo bash deploy/scripts/install_runtime_data.sh /tmp/runtime-data.tar.gz
set -euo pipefail
ARCHIVE="${1:?path to runtime-data.tar.gz}"
APP=/srv/nairobifloodwatch
STORE=/var/lib/nairobifloodwatch
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

tar -xzf "$ARCHIVE" -C "$WORK"
(cd "$WORK" && sha256sum --quiet -c SHA256SUMS)    # stops here if any file is damaged
echo "Checksums verified."

mkdir -p "$APP/data" "$APP/models" "$STORE"
cp -a "$WORK/repo/data/model_v1" "$APP/data/"
cp -a "$WORK/repo/models/nextday-proxy-v1" "$APP/models/"
for store in point_weather imerg_early operational_sources; do
  mkdir -p "$STORE/$store"
  cp -a "$WORK/store/$store/." "$STORE/$store/"
done
mkdir -p "$STORE/report_photos"
chown -R floodwatch:floodwatch "$STORE" "$APP/data/model_v1" "$APP/models/nextday-proxy-v1"
chmod 750 "$STORE"
echo "Installed research inputs into $APP and data stores into $STORE."
