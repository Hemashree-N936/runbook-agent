# Runbook: Failure Injection Test

1. Check current pod status in namespace "staging"
2. Scale deployment "web" down to 1 replica
3. Get replica count for deployment "definitely-does-not-exist"
