import * as vscode from 'vscode';
import { confirmCommand } from '../api_client/client';

export class ChatViewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'ai-coder.chatView';

    constructor(private readonly _extensionUri: vscode.Uri) {}

    public resolveWebviewView(webviewView: vscode.WebviewView) {
        webviewView.webview.options = { 
            enableScripts: true,
            localResourceRoots: [this._extensionUri]
        };

        const workspacePath = vscode.workspace.workspaceFolders?.[0].uri.fsPath.replace(/\\/g, '\\\\') || "";
        webviewView.webview.html = this._getHtmlForWebview(webviewView.webview, workspacePath);

        webviewView.webview.onDidReceiveMessage(async (data) => {
            if (data.type === 'executeCommand') {
                const result = await confirmCommand('accept');
                webviewView.webview.postMessage({ type: 'commandResult', value: result });
            } else if (data.type === 'rejectCommand') {
                await confirmCommand('reject');
            } else if (data.type === 'attachFile') {
                const uris = await vscode.window.showOpenDialog({ canSelectMany: true });
                if (uris) {
                    for (const uri of uris) {
                        const doc = await vscode.workspace.openTextDocument(uri);
                        webviewView.webview.postMessage({
                            type: 'fileAttached', name: uri.fsPath.split(/[/\\]/).pop(), content: doc.getText()
                        });
                    }
                }
            }
        });
    }

    private _getHtmlForWebview(webview: vscode.Webview, workspacePath: string) {
        return `<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline' ${webview.cspSource}; script-src 'unsafe-inline' https://cdn.jsdelivr.net; connect-src http://localhost:8000;">
            <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
            <style>
                body { display: flex; flex-direction: column; height: 100vh; margin: 0; padding: 10px; box-sizing: border-box; font-family: var(--vscode-font-family); color: var(--vscode-foreground); background: var(--vscode-sideBar-background); }
                #chat { flex-grow: 1; overflow-y: auto; margin-bottom: 10px; }
                .message { margin-bottom: 12px; border-bottom: 1px solid var(--vscode-widget-border); padding-bottom: 8px; }
                .user-label { color: var(--vscode-textLink-foreground); font-weight: bold; }
                .status-bar { font-size: 0.85em; color: var(--vscode-descriptionForeground); font-style: italic; margin-bottom: 8px; min-height: 1.2em; }
                
                .input-area { display: flex; flex-direction: column; gap: 8px; }
                .controls-row { display: flex; gap: 6px; align-items: center; }
                
                textarea { 
                    width: 100%; min-height: 45px; max-height: 200px; resize: none; 
                    background: var(--vscode-input-background); color: var(--vscode-input-foreground); 
                    border: 1px solid var(--vscode-input-border); padding: 8px; box-sizing: border-box;
                }
                
                select, button#attachBtn { 
                    background: var(--vscode-dropdown-background); color: var(--vscode-dropdown-foreground); 
                    border: 1px solid var(--vscode-dropdown-border); padding: 4px; 
                }
                
                button#sendBtn { background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 6px; cursor: pointer; flex-grow: 1; }
                button#stopBtn { background: var(--vscode-errorForeground); color: white; border: none; padding: 6px; cursor: pointer; display: none; }
                
                .badge { background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); padding: 2px 8px; border-radius: 10px; font-size: 0.8em; margin-right: 4px; display: inline-block; }
                .command-box { border: 1px solid var(--vscode-button-background); padding: 10px; margin-top: 8px; background: var(--vscode-editor-background); }
                pre { 
                    background: var(--vscode-editor-background); 
                    padding: 10px; 
                    border-radius: 4px; 
                    overflow-x: auto; 
                    border: 1px solid var(--vscode-widget-border); 
                    position: relative; 
                    cursor: pointer; 
                    transition: background 0.1s;
                }
                pre code {
                    background: transparent !important;
                    padding: 0 !important;
                    color: inherit;
                }
                pre:hover {
                    background: var(--vscode-editor-hoverHighlightBackground);
                }
                pre::after {
                    content: '🗐'; 
                    position: absolute;
                    top: 5px;
                    right: 8px;
                    opacity: 0;
                    transition: opacity 0.2s;
                    font-size: 14px;
                    pointer-events: none; 
                }
                pre:hover::after {
                    opacity: 0.7;
                }
                pre:active {
                    background: var(--vscode-editor-selectionHighlightBackground);
                }
                pre:active::after {
                    content: '🗸';
                }
            </style>
        </head>
        <body>
            <div id="chat"></div>
            <div id="status" class="status-bar"></div>
            <div id="attachments" style="margin-bottom: 5px;"></div>
            
            <div class="input-area">
                <div class="controls-row">
                    <select id="intent">
                        <option value="1">Learn</option>
                        <option value="2">Code</option>
                        <option value="3">Terminal</option>
                    </select>
                    <select id="mode">
                        <option value="fast">Fast</option>
                        <option value="thinking">Thinking</option>
                    </select>
                    <button id="attachBtn">📎 Attach</button>
                </div>
                <textarea id="prompt" placeholder="Ask AI..."></textarea>
                <div class="controls-row">
                    <button id="sendBtn">Send</button>
                    <button id="stopBtn">Stop</button>
                </div>
            </div>

            <script>
                const vscode = acquireVsCodeApi();
                const chat = document.getElementById('chat');
                chat.addEventListener('click', (e) => {
                    const pre = e.target.closest('pre');
                    if (pre) {
                        const codeElement = pre.querySelector('code') || pre;
                        const text = codeElement.innerText;
                        
                        navigator.clipboard.writeText(text).then(() => {
                            console.log('Code copied to clipboard');
                        }).catch(err => {
                            console.error('Failed to copy: ', err);
                        });
                    }
                });
                const promptInput = document.getElementById('prompt');
                const status = document.getElementById('status');
                const attachmentsDiv = document.getElementById('attachments');
                
                let pendingFiles = [];
                let currentAbortController = null;
                let streamBuffer = "";

                marked.setOptions({ gfm: true, breaks: true });

                function renderAttachments() {
                    attachmentsDiv.innerHTML = pendingFiles.map((f, i) => 
                        \`<span class="badge">\${f.name} <span onclick="removeFile(\${i})" style="cursor:pointer;margin-left:4px">×</span></span>\`
                    ).join('');
                }
                window.removeFile = (i) => { pendingFiles.splice(i, 1); renderAttachments(); };

                async function handleSend() {
                    const text = promptInput.value.trim();
                    if (!text && pendingFiles.length === 0) return;

                    const intent = document.getElementById('intent').value;
                    const mode = document.getElementById('mode').value;

                    // ОЧИЩЕННЯ ТА ОНОВЛЕННЯ UI
                    chat.innerHTML += \`<div class="message"><span class="user-label">You:</span><br>\${text}</div>\`;
                    promptInput.value = '';
                    document.getElementById('sendBtn').style.display = 'none';
                    document.getElementById('stopBtn').style.display = 'block';

                    let aiDiv = document.createElement('div');
                    aiDiv.className = 'message';
                    aiDiv.innerHTML = '<span class="user-label">AI:</span><div class="ai-content"></div>';
                    chat.appendChild(aiDiv);
                    const contentTarget = aiDiv.querySelector('.ai-content');

                    currentAbortController = new AbortController();
                    streamBuffer = "";
                    let fullAiText = "";

                    try {
                        const response = await fetch('http://localhost:8000/chat', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ 
                                query: text, 
                                context: { 
                                    intent: parseInt(intent), mode, 
                                    attached_files: pendingFiles,
                                    workspace_path: "${workspacePath}"
                                } 
                            }),
                            signal: currentAbortController.signal
                        });

                        const reader = response.body.getReader();
                        const decoder = new TextDecoder();

                        while (true) {
                            const { value, done } = await reader.read();
                            if (done) break;

                            streamBuffer += decoder.decode(value, { stream: true });
                            let lines = streamBuffer.split('\\n');
                            streamBuffer = lines.pop();

                            for (const line of lines) {
                                if (!line.trim()) continue;
                                try {
                                    const data = JSON.parse(line);
                                    if (data.type === 'chunk') {
                                        fullAiText += data.content;
                                        contentTarget.innerHTML = marked.parse(fullAiText);
                                    } else if (data.type === 'status') {
                                        status.innerText = data.content;
                                    } else if (data.type === 'command_proposal') {
                                        renderCommand(data.command, aiDiv);
                                    }
                                } catch (e) {}
                            }
                            chat.scrollTop = chat.scrollHeight;
                        }
                    } catch (err) {
                        status.innerText = err.name === 'AbortError' ? "Stopped." : "Error: " + err.message;
                    } finally {
                        document.getElementById('sendBtn').style.display = 'block';
                        document.getElementById('stopBtn').style.display = 'none';
                        status.innerText = "";
                        pendingFiles = [];
                        renderAttachments();
                    }
                }

                function renderCommand(cmd, container) {
                    const box = document.createElement('div');
                    box.className = 'command-box';
                    box.innerHTML = \`<div>Run in terminal: <code>\${cmd}</code>?</div>
                        <div style="margin-top:8px; display:flex; gap:8px;">
                            <button style="background:var(--vscode-button-background);color:white;border:none;padding:4px 8px;cursor:pointer;" onclick="confirmAction(true, this)">Accept</button>
                            <button style="background:var(--vscode-button-secondaryBackground);color:white;border:none;padding:4px 8px;cursor:pointer;" onclick="confirmAction(false, this)">Reject</button>
                        </div>\`;
                    container.appendChild(box);
                }

                window.confirmAction = (acc, btn) => {
                    vscode.postMessage({ type: acc ? 'executeCommand' : 'rejectCommand' });
                    btn.parentElement.parentElement.innerHTML = acc ? "✅ Command sent to terminal" : "❌ Command rejected";
                };

                // ВІДПРАВКА ПО ENTER
                promptInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                    }
                });

                document.getElementById('sendBtn').onclick = handleSend;
                document.getElementById('stopBtn').onclick = () => currentAbortController.abort();
                document.getElementById('attachBtn').onclick = () => vscode.postMessage({ type: 'attachFile' });
                
                window.addEventListener('message', e => {
                    if (e.data.type === 'fileAttached') {
                        pendingFiles.push(e.data);
                        renderAttachments();
                    } else if (e.data.type === 'commandResult') {
                        chat.innerHTML += \`<div class="message"><pre>\${e.data.value}</pre></div>\`;
                        chat.scrollTop = chat.scrollHeight;
                    }
                });
            </script>
        </body>
        </html>`;
    }
}