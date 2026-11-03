#!/usr/bin/env bash
# Build the zip to upload at https://plugins.qgis.org/plugins/add/ (top-level folder = plugin folder).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m unittest discover -s pcp_eia_pollution_modeling/tests -t .
ver=$(grep '^version=' pcp_eia_pollution_modeling/metadata.txt | cut -d= -f2)
out="pcp_eia_pollution_modeling_${ver}.zip"
rm -f "$out"
zip -qr "$out" pcp_eia_pollution_modeling -x '*__pycache__*' '*.pyc'
echo "built $out"
