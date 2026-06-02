import * as vscode from 'vscode';

export async function openPanel(backendUrl: string): Promise<void> {
  try {
    // VS Code built-in Simple Browser — supports full HTTP pages including React SPAs
    await vscode.commands.executeCommand('simpleBrowser.show', backendUrl);
  } catch {
    // Fallback: open in system browser if Simple Browser unavailable
    await vscode.env.openExternal(vscode.Uri.parse(backendUrl));
  }
}
