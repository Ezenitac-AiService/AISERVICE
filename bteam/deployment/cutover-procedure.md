# Green candidate route procedure

This is an operator-run procedure. It does not create approvals and it does not modify the active Blue gateway.

1. Verify `docker compose -f docker-compose.green.yml config` and the four health endpoints.
2. Validate `deployment_gate_contract.json` artifacts and the external `CUTOVER_APPROVED` record.
3. Run `nginx -t -c deployment/nginx.green.conf` against the candidate file only.
4. Capture the current active configuration and health probes as the rollback checkpoint.
5. Apply the approved configuration atomically, reload, and probe every route.
6. On any threshold breach, restore the captured configuration and route to Blue. Do not stop Blue during soak.

The minimum rollback evidence is the Blue route snapshot, Green route snapshot, probe output, operator identity, and UTC timestamps.

