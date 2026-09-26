# Runbook: Cleanup Old Deployment

1. Check current pod status in namespace "staging"
2. Scale deployment "web-v1" down to 0 replicas
3. Delete deployment "web-v1" permanently

