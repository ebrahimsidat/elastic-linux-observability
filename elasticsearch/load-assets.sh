#!/usr/bin/env bash
# Load the ILM policy into Elasticsearch and create the disk usage alert rule in Kibana.
#
# Usage: ES_URL=http://localhost:9200 KIBANA_URL=http://localhost:5601 \
#        ES_USERNAME=elastic ES_PASSWORD=... ./elasticsearch/load-assets.sh
set -euo pipefail

: "${ES_URL:=http://localhost:9200}"
: "${KIBANA_URL:=http://localhost:5601}"
: "${ES_USERNAME:=elastic}"
: "${ES_PASSWORD:?Set ES_PASSWORD}"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Creating ILM policy metrics-30d"
curl --fail --silent --show-error -u "${ES_USERNAME}:${ES_PASSWORD}" \
  -X PUT "${ES_URL}/_ilm/policy/metrics-30d" \
  -H "Content-Type: application/json" \
  --data-binary "@${here}/ilm-metrics-30d.json"
echo

echo "Creating Kibana alert rule"
curl --fail --silent --show-error -u "${ES_USERNAME}:${ES_PASSWORD}" \
  -X POST "${KIBANA_URL}/api/alerting/rule" \
  -H "Content-Type: application/json" \
  -H "kbn-xsrf: true" \
  --data-binary "@${here}/kibana-rule-disk-usage.json"
echo
