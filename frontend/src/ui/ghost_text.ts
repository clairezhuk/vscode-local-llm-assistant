import * as vscode from 'vscode';
import { fetchCompletions } from '../api_client/client';

export class GhostTextProvider implements vscode.InlineCompletionItemProvider {
    async provideInlineCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        context: vscode.InlineCompletionContext,
        token: vscode.CancellationToken
    ): Promise<vscode.InlineCompletionItem[]> {
        
        // Limit context to the last 15 lines to speed up inference
        const startLine = Math.max(0, position.line - 15);
        const startPos = new vscode.Position(startLine, 0);
        const textBeforeCursor = document.getText(new vscode.Range(startPos, position));
        
        if (textBeforeCursor.trim() === '') {
            return [];
        }

        const startTime = Date.now();
        const completionText = await fetchCompletions(textBeforeCursor);
        const elapsed = (Date.now() - startTime) / 1000;
        
        console.log(`[GhostText] Received in ${elapsed}s: '${completionText}'`);

        if (!completionText || token.isCancellationRequested) {
            return [];
        }

        return [new vscode.InlineCompletionItem(completionText, new vscode.Range(position, position))];
    }
}