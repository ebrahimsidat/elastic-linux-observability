# Operational guidance

## Choosing thresholds

| File system type | Suggested warning / critical | Reason |
|---|---|---|
| Root and OS (`/`, `/usr`) | 80% / 90% | Default; leaves room for package updates and logs |
| Logs (`/var/log`) | 75% / 85% | Grows quickly during incidents, exactly when space matters most |
| Databases (`/var/lib/pgsql`, `/var/lib/mysql`) | 70% / 85% | Vacuum, reindex and backup operations temporarily need extra space |
| Large data volumes (multi-TB) | 90% / 95% | Percentages hide large absolute free space on big volumes |

Run several fsmon checks with different thresholds and `--host` or `--exclude-mount` filters when tiers need different limits.

## Scheduling examples

**cron, emailing only when there is a problem:**

```cron
*/10 * * * * fsmon --format nagios || echo "fsmon exit $?" | mail -s "Disk capacity alert" ops@example.com
```

**Nagios / Icinga command definition:**

```text
define command {
    command_name    check_fsmon
    command_line    /usr/local/bin/fsmon --format nagios --warning $ARG1$ --critical $ARG2$
}
```

**CI/CD gate before a deployment that writes large artefacts:**

```bash
fsmon --host "app-*" --critical 85 --format json > capacity.json || {
  echo "Insufficient disk capacity on target hosts"; exit 1; }
```

## Exit codes

| Code | Status | Meaning |
|---|---|---|
| 0 | OK | All file systems are below the warning threshold |
| 1 | WARNING | At least one file system is at or above the warning threshold |
| 2 | CRITICAL | At least one file system is at or above the critical threshold |
| 3 | UNKNOWN | No data in the time window, authentication failure, or Elasticsearch unreachable |

An UNKNOWN result should alert as well: a host that stops reporting is often a bigger problem than a full disk.

## Data retention

The included ILM policy keeps raw metrics for 30 days, which covers month-over-month capacity trending. For longer
trend analysis, keep downsampled data instead of raw samples (Elasticsearch downsampling or a transform that stores
daily maximum usage per host and mount point).

## Least-privilege API key for fsmon

fsmon only needs read access to the Metricbeat indices:

```json
POST /_security/api_key
{
  "name": "fsmon",
  "role_descriptors": {
    "fsmon_read": {
      "indices": [{ "names": ["metricbeat-*"], "privileges": ["read"] }]
    }
  }
}
```

Set the returned `encoded` value as `ES_API_KEY`.
