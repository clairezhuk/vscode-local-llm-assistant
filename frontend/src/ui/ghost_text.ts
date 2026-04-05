import * as vscode from 'vscode';
import { fetchCompletions } from '../api_client/client';

export class GhostTextProvider implements vscode.InlineCompletionItemProvider {
    async provideInlineCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        context: vscode.InlineCompletionContext,
        token: vscode.CancellationToken
    ): Promise<vscode.InlineCompletionItem[]> {
        const textBeforeCursor = document.getText(new vscode.Range(new vscode.Position(0, 0), position));
        
        const completionText = await fetchCompletions(textBeforeCursor);
        
        if (!completionText) {
            return [];
        }

        return [new vscode.InlineCompletionItem(completionText, new vscode.Range(position, position))];
    }
}