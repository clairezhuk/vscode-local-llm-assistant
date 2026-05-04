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
        <head>
            <style>
                body {
                    display: flex;
                    flex-direction: column;
                    height: 100vh;
                    margin: 0;
                    padding: 10px;
                    box-sizing: border-box;
                }
                #chat {
                    flex-grow: 1;
                    overflow-y: auto;
                    margin-bottom: 10px;
                    word-wrap: break-word;
                }
                .input-area {
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                }
                textarea {
                    width: 100%;
                    min-height: 36px;
                    max-height: 200px;
                    box-sizing: border-box;
                    resize: none;
                    overflow-y: hidden;
                    background-color: var(--vscode-input-background);
                    color: var(--vscode-input-foreground);
                    border: 1px solid var(--vscode-input-border);
                    padding: 8px;
                    font-family: inherit;
                    border-radius: 2px;
                }
                textarea:focus {
                    outline: 1px solid var(--vscode-focusBorder);
                    border-color: var(--vscode-focusBorder);
                }
                button {
                    background-color: var(--vscode-button-background);
                    color: var(--vscode-button-foreground);
                    border: none;
                    padding: 8px;
                    cursor: pointer;
                    border-radius: 2px;
                }
                button:hover {
                    background-color: var(--vscode-button-hoverBackground);
                }
            </style>
        </head>
        <body>
            <div id="chat"></div>
            <div class="input-area">
                <textarea id="prompt" rows="1" placeholder="Ask AI..."></textarea>
                <button id="sendBtn">Send</button>
            </div>
            <script>
                const vscode = acquireVsCodeApi();
                const promptInput = document.getElementById('prompt');
                const sendBtn = document.getElementById('sendBtn');
                const chat = document.getElementById('chat');

                function sendMessage() {
                    const text = promptInput.value.trim();
                    if (!text) return;
                    
                    chat.innerHTML += '<div style="margin-bottom: 8px;"><b>User:</b> ' + text + '</div>';
                    vscode.postMessage({ type: 'sendPrompt', value: text });
                    
                    promptInput.value = '';
                    promptInput.style.height = 'auto';
                    chat.scrollTop = chat.scrollHeight;
                }

                promptInput.addEventListener('input', function() {
                    this.style.height = 'auto';
                    this.style.height = (this.scrollHeight) + 'px';
                });

                promptInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        sendMessage();
                    }
                });

                sendBtn.addEventListener('click', sendMessage);

                window.addEventListener('message', event => {
                    const message = event.data;
                    if (message.type === 'addResponse') {
                        chat.innerHTML += '<div style="margin-bottom: 12px; color: var(--vscode-textPreformat-foreground);"><b>AI:</b> ' + message.value + '</div>';
                        chat.scrollTop = chat.scrollHeight;
                    }
                });
            </script>
        </body>
        </html>`;
    }
}