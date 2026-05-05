import * as vscode from 'vscode';
import { sendQuery } from '../api_client/client';

export class ChatViewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'ai-coder.chatView';

    constructor(private readonly _extensionUri: vscode.Uri) {}

    public resolveWebviewView(webviewView: vscode.WebviewView) {
        webviewView.webview.options = { 
            enableScripts: true,
            localResourceRoots: [this._extensionUri]
        };
        webviewView.webview.html = this._getHtmlForWebview();

        webviewView.webview.onDidReceiveMessage(async (data) => {
            if (data.type === 'sendPrompt') {
                const response = await sendQuery(data.value, data.context);
                webviewView.webview.postMessage({ type: 'addResponse', value: response });
            } else if (data.type === 'attachFile') {
                const uris = await vscode.window.showOpenDialog({
                    canSelectMany: true,
                    openLabel: 'Attach to AI Context'
                });
                
                if (uris && uris.length > 0) {
                    for (const uri of uris) {
                        try {
                            const document = await vscode.workspace.openTextDocument(uri);
                            webviewView.webview.postMessage({
                                type: 'fileAttached',
                                name: uri.fsPath.split(/[/\\]/).pop(),
                                content: document.getText()
                            });
                        } catch (e) {
                            console.error("Failed to read file", e);
                        }
                    }
                }
            }
        });
    }

    private _getHtmlForWebview() {
        return `<!DOCTYPE html>
        <html lang="en">
        <head>
            <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
            <style>
                body {
                    display: flex;
                    flex-direction: column;
                    height: 100vh;
                    margin: 0;
                    padding: 10px;
                    box-sizing: border-box;
                    font-family: var(--vscode-font-family);
                }
                #chat {
                    flex-grow: 1;
                    overflow-y: auto;
                    margin-bottom: 10px;
                    word-wrap: break-word;
                }
                pre {
                    background-color: var(--vscode-editor-background);
                    border: 1px solid var(--vscode-widget-border);
                    padding: 10px;
                    border-radius: 4px;
                    overflow-x: auto;
                }
                code {
                    font-family: var(--vscode-editor-font-family);
                    color: var(--vscode-textPreformat-foreground);
                }
                .message {
                    margin-bottom: 12px;
                }
                .user-message {
                    font-weight: bold;
                    color: var(--vscode-textLink-foreground);
                }
                .input-area {
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                }
                .input-controls {
                    display: flex;
                    gap: 8px;
                }
                textarea {
                    flex-grow: 1;
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
                    padding: 8px 12px;
                    cursor: pointer;
                    border-radius: 2px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                button:hover {
                    background-color: var(--vscode-button-hoverBackground);
                }
                #attachments {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 4px;
                }
                .attachment-badge {
                    background-color: var(--vscode-badge-background);
                    color: var(--vscode-badge-foreground);
                    padding: 2px 6px;
                    border-radius: 10px;
                    font-size: 11px;
                    display: flex;
                    align-items: center;
                    gap: 4px;
                }
                .remove-attachment {
                    cursor: pointer;
                    font-weight: bold;
                }
            </style>
        </head>
        <body>
            <div id="chat"></div>
            <div class="input-area">
                <div id="attachments"></div>
                <div class="input-controls">
                    <button id="attachBtn" title="Attach File">📎</button>
                    <textarea id="prompt" rows="1" placeholder="Ask AI..."></textarea>
                    <button id="sendBtn">Send</button>
                </div>
            </div>
            <script>
                const vscode = acquireVsCodeApi();
                const promptInput = document.getElementById('prompt');
                const sendBtn = document.getElementById('sendBtn');
                const attachBtn = document.getElementById('attachBtn');
                const chat = document.getElementById('chat');
                const attachmentsDiv = document.getElementById('attachments');

                let pendingFiles = [];

                marked.setOptions({
                    breaks: true, 
                    gfm: true     
                });

                function renderAttachments() {
                    attachmentsDiv.innerHTML = '';
                    pendingFiles.forEach((file, index) => {
                        const badge = document.createElement('div');
                        badge.className = 'attachment-badge';
                        badge.innerHTML = \`\${file.name} <span class="remove-attachment" data-index="\${index}">×</span>\`;
                        attachmentsDiv.appendChild(badge);
                    });

                    document.querySelectorAll('.remove-attachment').forEach(btn => {
                        btn.addEventListener('click', (e) => {
                            const index = e.target.getAttribute('data-index');
                            pendingFiles.splice(index, 1);
                            renderAttachments();
                        });
                    });
                }

                function sendMessage() {
                    const text = promptInput.value.trim();
                    if (!text && pendingFiles.length === 0) return;
                    
                    let fileNames = pendingFiles.map(f => f.name).join(', ');
                    let displayMsg = text;
                    if (fileNames) {
                        displayMsg = \`[Attached: \${fileNames}]<br>\` + text;
                    }

                    chat.innerHTML += '<div class="message"><span class="user-message">User:</span> ' + displayMsg + '</div>';
                    
                    vscode.postMessage({ 
                        type: 'sendPrompt', 
                        value: text,
                        context: { attached_files: pendingFiles }
                    });
                    
                    promptInput.value = '';
                    promptInput.style.height = 'auto';
                    pendingFiles = [];
                    renderAttachments();
                    chat.scrollTop = chat.scrollHeight;
                }

                attachBtn.addEventListener('click', () => {
                    vscode.postMessage({ type: 'attachFile' });
                });

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
                        const htmlContent = marked.parse(message.value);
                        chat.innerHTML += '<div class="message"><b>AI:</b><br>' + htmlContent + '</div>';
                        chat.scrollTop = chat.scrollHeight;
                    } else if (message.type === 'fileAttached') {
                        pendingFiles.push({ name: message.name, content: message.content });
                        renderAttachments();
                    }
                });
            </script>
        </body>
        </html>`;
    }
}