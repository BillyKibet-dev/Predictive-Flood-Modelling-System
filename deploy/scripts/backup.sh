#!/usr/bin/env bash
# Nightly backup: database + data stores (photos, weather evidence), kept 14 days.
# Installed as /etc/cron.d/nairobifloodwatch-backup (deploy/AZURE_DEPLOYMENT.md, step 12).
set -euo pipefail
DEST=/var/backups/nairobifloodwatch
STAMP="$(date -u +%Y%m%dT%H%MZ)"
mkdir -p "$DEST"
chmod 700 "$DEST"
sudo -u postgres pg_dump -Fc nairobifloodwatch > "$DEST/db-$STAMP.dump"
tar -czf "$DEST/stores-$STAMP.tar.gz" -C /var/lib nairobifloodwatch
find "$DEST" -type f -mtime +14 -delete
echo "Backup $STAMP written to $DEST"
