# Runbook: Cleanup Old Deployment and Database

1. Check current pod status in namespace "staging"
2. Scale deployment "web-v1" down to 0 replicas
3. Delete deployment "web-v1" permanently
4. Drop the old_sessions table from the database
