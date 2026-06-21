import * as vscode from "vscode";
import { WakeEvent } from "./wsClient";

export async function notifyWake(event: WakeEvent): Promise<void> {
  const choice = await vscode.window.showInformationMessage(
    `Your turn in ${event.thread_id}`,
    "Respond now"
  );
  if (choice !== "Respond now") {
    return;
  }
  await openProjection(event.thread_id);
}

async function openProjection(threadId: string): Promise<void> {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri;
  if (!root) {
    return;
  }
  const uri = vscode.Uri.joinPath(root, "data", "projections", threadId, "thread.md");
  try {
    const doc = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(doc);
  } catch {
    void vscode.window.showWarningMessage(`Projection not found for ${threadId}.`);
  }
}
