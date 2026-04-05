import * as vscode from 'vscode';
import { sendQuery } from '../api_client/client';

export class ChatViewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'ai-coder.chatView';

    constructor(private readonly _extensionUri: vscode.Uri) {}

    public resolveWebviewView(webviewView: vscode.WebviewView) {
        webviewView.webview.options = { enableScripts: true };
        webviewView.webview.html = this._getHtmlForWebview();

        webviewView.webview.onDidReceiveMessage(async (data) => {
            if (data.type === 'sendPrompt') {
                const response = await sendQuery(data.value, {});
                webviewView.webview.postMessage({ type: 'addResponse', value: response });
            }
        });
    }

    private _getHtmlForWebview() {
        return `<!DOCTYPE html>
        <html lang="en">
        <body>
            <div id="chat"></div>
            <textarea id="prompt" rows="3"></textarea>
            <button id="sendBtn">Send</button>
            <script>
                const vscode = acquireVsCodeApi();
                document.getElementById('sendBtn').addEventListener('click', () => {
                    const text = document.getElementById('prompt').value;
                    document.getElementById('chat').innerHTML += '<b>User:</b> ' + text + '<br>';
                    vscode.postMessage({ type: 'sendPrompt', value: text });
                    document.getElementById('prompt').value = '';
                });
                window.addEventListener('message', event => {
                    const message = event.data;
                    if (message.type === 'addResponse') {
                        document.getElementById('chat').innerHTML += '<b>AI:</b> ' + message.value + '<br>';
                    }
                });
            </script>
        </body>
        </html>`;
    }
}