import * as vscode from "vscode";
import { AgentWakeClient } from "./wsClient";

const TOKEN_KEY = "agentSlack.routerToken";
let client: AgentWakeClient | undefined;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const output = vscode.window.createOutputChannel("Agent Slack Router");
  context.subscriptions.push(output);
  context.subscriptions.push(
    vscode.commands.registerCommand("agentSlack.setRouterToken", () =>
      setRouterToken(context)
    ),
    vscode.commands.registerCommand("agentSlack.connect", () =>
      connectRouter(context, output)
    )
  );
  await connectRouter(context, output, false);
}

export function deactivate(): void {
  client?.dispose();
}

async function setRouterToken(context: vscode.ExtensionContext): Promise<void> {
  const token = await vscode.window.showInputBox({
    prompt: "Router bearer token",
    password: true,
    ignoreFocusOut: true
  });
  if (!token) {
    return;
  }
  await context.secrets.store(TOKEN_KEY, token);
  void vscode.window.showInformationMessage("Agent Slack router token saved.");
}

async function connectRouter(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel,
  notifyMissing = true
): Promise<void> {
  const config = vscode.workspace.getConfiguration("agentSlack");
  const routerUrl = config.get<string>("routerUrl", "ws://127.0.0.1:8000");
  const threadId = config.get<string>("threadId", "").trim();
  const agent = config.get<string>("agent", "codex");
  const token = await context.secrets.get(TOKEN_KEY);
  if (!token || !threadId) {
    if (notifyMissing) {
      void vscode.window.showWarningMessage("Set router token and thread id first.");
    }
    return;
  }
  client?.dispose();
  client = new AgentWakeClient(routerUrl, threadId, token, output);
  output.appendLine(`Watching ${threadId} for ${agent}; identity comes from token.`);
  client.connect();
}
