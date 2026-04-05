import * as vscode from 'vscode';
import { ChatViewProvider } from './ui/chat_view';
import { GhostTextProvider } from './ui/ghost_text';

export function activate(context: vscode.ExtensionContext) {
    const chatProvider = new ChatViewProvider(context.extensionUri);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(ChatViewProvider.viewType, chatProvider)
    );

    const ghostTextProvider = new GhostTextProvider();
    context.subscriptions.push(
        vscode.languages.registerInlineCompletionItemProvider({ pattern: '**' }, ghostTextProvider)
    );
}