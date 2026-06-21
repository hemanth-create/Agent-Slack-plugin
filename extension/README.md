# Agent Slack Router Extension

Minimal P4 M1 smoke extension for local router wake notifications.

## Setup

```powershell
cd extension
npm install
npm run compile
```

## VS Code Smoke

1. Start the backend from the repo root.
2. Open this repo in VS Code and press F5 to launch an Extension Development Host.
3. In the dev host, run `Agent Slack: Set Router Token` and paste the bearer token for the agent you want to wake.
4. Set `agentSlack.threadId` to the router thread id and leave `agentSlack.routerUrl` as `ws://127.0.0.1:8000` unless the backend runs elsewhere.
5. Run `Agent Slack: Connect Router`.
6. Submit a turn that flips the baton to this token's agent.

The dev host should show `Your turn in <thread>`. The extension never puts the token in a URL; it sends the bearer in the WebSocket `Authorization` header with a loopback `Origin`.
