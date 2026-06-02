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

        webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);

        webviewView.webview.onDidReceiveMessage(async (data) => {
            switch (data.type) {
                case 'attachFile':
                    const uris = await vscode.window.showOpenDialog({
                        canSelectMany: true,
                        openLabel: 'Attach to AI Context'
                    });
                    if (uris) {
                        for (const uri of uris) {
                            const document = await vscode.workspace.openTextDocument(uri);
                            webviewView.webview.postMessage({
                                type: 'fileAttached',
                                name: uri.fsPath.split(/[/\\]/).pop(),
                                content: document.getText()
                            });
                        }
                    }
                    break;
                case 'executeCommand':
                    const result = await confirmCommand('accept');
                    webviewView.webview.postMessage({ type: 'commandResult', value: result });
                    break;
                case 'rejectCommand':
                    await confirmCommand('reject');
                    break;
            }
        });
    }

    private _getHtmlForWebview(webview: vscode.Webview) {
        return `<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
            <style>${this._getStyles()}</style>
        </head>
        <body>
            ${this._getHtmlStructure()}
            <script>${this._getScript()}</script>
        </body>
        </html>`;
    }

    private _getStyles() {
        return `
            body { display: flex; flex-direction: column; height: 100vh; margin: 0; padding: 10px; box-sizing: border-box; font-family: var(--vscode-font-family); color: var(--vscode-foreground); }
            #chat { flex-grow: 1; overflow-y: auto; margin-bottom: 10px; }
            .message { margin-bottom: 15px; border-bottom: 1px solid var(--vscode-widget-border); padding-bottom: 10px; }
            .user-msg { color: var(--vscode-textLink-foreground); font-weight: bold; margin-bottom: 5px; }
            .ai-msg { background: var(--vscode-editor-background); padding: 5px; border-radius: 4px; }
            
            .status-bar { font-size: 0.85em; color: var(--vscode-descriptionForeground); margin-bottom: 10px; min-height: 20px; }
            .plan-container { background: var(--vscode-welcomePage-tileBackground); padding: 8px; border-radius: 4px; margin: 5px 0; font-size: 0.9em; }
            
            .input-area { display: flex; flex-direction: column; gap: 8px; background: var(--vscode-sideBar-background); }
            .controls-row { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
            
            textarea { width: 100%; min-height: 40px; max-height: 200px; resize: none; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); padding: 8px; box-sizing: border-box; }
            
            button { cursor: pointer; border: none; padding: 6px 12px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); border-radius: 2px; }
            button:hover { background: var(--vscode-button-hoverBackground); }
            #stopBtn { background: var(--vscode-errorForeground); display: none; }
            
            select { background: var(--vscode-dropdown-background); color: var(--vscode-dropdown-foreground); border: 1px solid var(--vscode-dropdown-border); padding: 4px; }
            
            .command-box { border: 1px solid var(--vscode-button-background); padding: 10px; margin: 10px 0; border-radius: 4px; }
            .badge { background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); padding: 2px 6px; border-radius: 10px; font-size: 0.8em; margin-right: 4px; }
            pre { background: #1e1e1e; padding: 10px; overflow-x: auto; border-radius: 4px; }
            code { font-family: var(--vscode-editor-font-family); }
        `;
    }

    private _getHtmlStructure() {
        return `
            <div id="chat"></div>
            <div id="status" class="status-bar"></div>
            <div id="attachments" style="margin-bottom: 8px;"></div>
            
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
                    <button id="attachBtn" title="Attach Files">📎</button>
                </div>
                <textarea id="prompt" placeholder="Ask AI... (Shift+Enter for new line)"></textarea>
                <div class="controls-row">
                    <button id="sendBtn" style="flex-grow: 1;">Send</button>
                    <button id="stopBtn">Stop</button>
                </div>
            </div>
        `;
    }

    private _getScript() {
        return `
            const vscode = acquireVsCodeApi();
            const chat = document.getElementById('chat');
            const status = document.getElementById('status');
            const promptInput = document.getElementById('prompt');
            const sendBtn = document.getElementById('sendBtn');
            const stopBtn = document.getElementById('stopBtn');
            const attachBtn = document.getElementById('attachBtn');
            const attachmentsDiv = document.getElementById('attachments');

            let pendingFiles = [];
            let currentAbortController = null;

            // Налаштування marked
            marked.setOptions({ gfm: true, breaks: true });

            function renderAttachments() {
                attachmentsDiv.innerHTML = pendingFiles.map((f, i) => 
                    \`<span class="badge">\${f.name} <span onclick="removeFile(\${i})" style="cursor:pointer">×</span></span>\`
                ).join('');
            }

            window.removeFile = (i) => { pendingFiles.splice(i, 1); renderAttachments(); };

            async function handleSend() {
                const query = promptInput.value.trim();
                if (!query && pendingFiles.length === 0) return;

                const intent = document.getElementById('intent').value;
                const mode = document.getElementById('mode').value;

                // UI update
                chat.innerHTML += \`<div class="message"><div class="user-msg">You:</div>\${query}</div>\`;
                promptInput.value = '';
                sendBtn.style.display = 'none';
                stopBtn.style.display = 'block';
                
                currentAbortController = new AbortController();
                let aiMessageDiv = document.createElement('div');
                aiMessageDiv.className = 'message';
                aiMessageDiv.innerHTML = '<div class="user-msg">AI:</div><div class="ai-content"></div>';
                chat.appendChild(aiMessageDiv);
                const contentTarget = aiMessageDiv.querySelector('.ai-content');

                try {
                    const response = await fetch('http://localhost:8000/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            query, 
                            context: { intent: parseInt(intent), mode, attached_files: pendingFiles } 
                        }),
                        signal: currentAbortController.signal
                    });

                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let fullText = "";

                    while (true) {
                        const { value, done } = await reader.read();
                        if (done) break;

                        const chunk = decoder.decode(value);
                        const lines = chunk.split('\\n');

                        for (const line of lines) {
                            if (!line.trim()) continue;
                            try {
                                const data = JSON.parse(line);
                                if (data.type === 'status') {
                                    status.innerText = data.content;
                                } else if (data.type === 'plan') {
                                    contentTarget.innerHTML += \`<div class="plan-container"><b>Plan:</b><br>\${data.content.join('<br>')}</div>\`;
                                } else if (data.type === 'start_content') {
                                    if (data.clear) { fullText = ""; contentTarget.innerHTML = ""; }
                                } else if (data.type === 'chunk') {
                                    fullText += data.content;
                                    contentTarget.innerHTML = marked.parse(fullText);
                                } else if (data.type === 'command_proposal') {
                                    renderCommandBox(data.command, aiMessageDiv);
                                }
                            } catch (e) { console.error("JSON parse error", e, line); }
                        }
                        chat.scrollTop = chat.scrollHeight;
                    }
                } catch (err) {
                    if (err.name === 'AbortError') status.innerText = "Generation stopped.";
                    else status.innerText = "Connection error.";
                } finally {
                    sendBtn.style.display = 'block';
                    stopBtn.style.display = 'none';
                    status.innerText = "";
                    pendingFiles = [];
                    renderAttachments();
                }
            }

            function renderCommandBox(cmd, container) {
                const box = document.createElement('div');
                box.className = 'command-box';
                box.innerHTML = \`
                    <div>Execute: <code>\${cmd}</code>?</div>
                    <div style="display:flex; gap:8px; margin-top:8px;">
                        <button onclick="confirmCmd(true, this)">Accept</button>
                        <button style="background:var(--vscode-button-secondaryBackground)" onclick="confirmCmd(false, this)">Reject</button>
                    </div>\`;
                container.appendChild(box);
            }

            window.confirmCmd = (accept, btn) => {
                if (accept) vscode.postMessage({ type: 'executeCommand' });
                else vscode.postMessage({ type: 'rejectCommand' });
                btn.parentElement.parentElement.innerHTML = accept ? "✅ Command executed" : "❌ Command rejected";
            };

            sendBtn.onclick = handleSend;
            stopBtn.onclick = () => currentAbortController?.abort();
            attachBtn.onclick = () => vscode.postMessage({ type: 'attachFile' });
            
            promptInput.onkeydown = (e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
            };

            window.addEventListener('message', event => {
                if (event.data.type === 'fileAttached') {
                    pendingFiles.push({ name: event.data.name, content: event.data.content });
                    renderAttachments();
                } else if (event.data.type === 'commandResult') {
                    chat.innerHTML += \`<div class="message"><pre>\${event.data.value}</pre></div>\`;
                    chat.scrollTop = chat.scrollHeight;
                }
            });
        `;
    }
}