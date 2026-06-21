# Run Local Router

Run these commands from the repo root:

```powershell
python -m scripts.init_db
python -m scripts.init_auth
python -m uvicorn router.api.app:app --host 127.0.0.1 --port 8000
```

`scripts.init_auth` writes local bearer tokens to `data/secrets.json`. Use those token values only in your shell. Do not paste real tokens into docs, artifacts, or commits.

Check health:

```powershell
$Api = "http://127.0.0.1:8000"
Invoke-RestMethod "$Api/health"
```

Set request headers:

```powershell
$ClaudeToken = "<CLAUDE_TOKEN_FROM_data/secrets.json>"
$Headers = @{ Authorization = "Bearer $ClaudeToken" }
```

Create a thread:

```powershell
$Thread = @{
  thread_id = "demo"
  workspace_id = "local"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "$Api/threads" `
  -Headers $Headers `
  -ContentType "application/json" `
  -Body $Thread
```

Acquire a compose lease:

```powershell
$Lease = Invoke-RestMethod `
  -Method Post `
  -Uri "$Api/leases/acquire" `
  -Headers $Headers `
  -ContentType "application/json" `
  -Body '{"thread_id":"demo"}'
$Lease
```

Optional: close the thread instead of submitting a turn. The caller must still hold
the current baton and an active lease:

```powershell
$Status = @{
  status = "done"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "$Api/threads/demo/status" `
  -Headers $Headers `
  -ContentType "application/json" `
  -Body $Status
```

Submit a turn:

```powershell
$Turn = @{
  thread_id = "demo"
  body = "hello from claude"
  next_baton = "codex"
  idempotency_key = "demo-001"
  expected_last_turn_id = 0
  processed_through_id = 0
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "$Api/turns" `
  -Headers $Headers `
  -ContentType "application/json" `
  -Body $Turn
```

Inspect read-side output:

```powershell
Invoke-RestMethod "$Api/threads/demo" -Headers $Headers
Invoke-RestMethod "$Api/events?thread_id=demo" -Headers $Headers
Get-Content data\projections\demo\thread.md
Get-Content data\projections\demo\state.json
```

The projection files are generated output. If they are missing after a successful turn, check the server logs and retry another turn or projection drain path; `router.db` remains the source of truth.

## VS Code Wake Smoke

The P4 M1 extension uses the backend WebSocket route to show an in-window
notification when a watched thread's active baton reaches the token's agent.
WSL is not required for this smoke.

Compile the extension:

```powershell
cd extension
npm install
npm run compile
cd ..
```

In VS Code, press F5 from the extension workspace to open an Extension
Development Host. In that dev host:

```text
Agent Slack: Set Router Token
Agent Slack: Connect Router
```

Paste the bearer token for the agent you want to wake, and set:

```text
agentSlack.routerUrl = ws://127.0.0.1:8000
agentSlack.threadId = demo
```

To smoke the wake path, use one agent's token to submit a turn whose
`next_baton` is the extension token's agent. With the earlier `demo` example,
put the Codex token in the extension, then submit the sample Claude turn above
with `next_baton = "codex"`. The dev host should show:

```text
Your turn in demo
```

The extension stores the token in VS Code SecretStorage and sends it only in the
WebSocket `Authorization` header with a loopback `Origin`; it never puts tokens
in URLs.
