# SysKernel-AI Execution & Safety Policy

## 1. Action Allowlist (Read-Only Default)
- Passive Monitoring (No authorization needed): systemctl status, dmesg, journalctl, ps aux, df -h, ss -tulpn.
- Remediations (Requires Safety Layer Check): systemctl restart <service>, systemctl reload <service>, kill -9 <PID> (specific targeted PID only).
- Strictly Forbidden: Any recursive deletions (rm), wildcard path modifications, system file editing, or user privilege alterations.

## 2. Risk Tiers & Human-in-the-Loop Approval Gate
- LOW Risk: Restarting non-critical user-space service.
- MEDIUM/HIGH Risk: Process termination (kill), service stop, cache flushing. Requires explicit admin approval via Web Dashboard.

## 3. Blast-Radius Control
- Maximum Actions per Incident: 2 commands.
- Resolution Check Window: 10 seconds.
- Auto-Rollback: If anomaly metric (CPU/RAM/Error rate) does not return to baseline within 10 seconds, state changes are rolled back automatically.