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
                            type: 'fileAttached',
                            name: uri.fsPath.split(/[/\\]/).pop(),
                            content: doc.getText()
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
                body { display: flex; flex-direction: column; height: 100vh; margin: 0; padding: 10px; box-sizing: border-box; font-family: var(--vscode-font-family); color: var(--vscode-foreground); }
                #chat { flex-grow: 1; overflow-y: auto; margin-bottom: 10px; }
                .message { margin-bottom: 15px; border-bottom: 1px solid var(--vscode-widget-border); padding-bottom: 10px; }
                .status-bar { font-size: 0.8em; color: var(--vscode-descriptionForeground); margin-bottom: 5px; }
                .input-area { display: flex; flex-direction: column; gap: 8px; }
                .controls { display: flex; gap: 4px; }
                textarea { width: 100%; min-height: 40px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); }
                button { background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 4px 8px; cursor: pointer; }
                .command-box { border: 1px solid var(--vscode-button-background); padding: 8px; margin-top: 5px; }
            </style>
        </head>
        <body>
            <div id="chat"></div>
            <div id="status" class="status-bar"></div>
            <div class="input-area">
                <div class="controls">
                    <select id="intent"><option value="1">Learn</option><option value="2">Code</option><option value="3">Terminal</option></select>
                    <select id="mode"><option value="fast">Fast</option><option value="thinking">Thinking</option></select>
                    <button id="attachBtn">📎</button>
                </div>
                <textarea id="prompt" placeholder="Ask AI..."></textarea>
                <button id="sendBtn">Send</button>
                <button id="stopBtn" style="display:none; background:var(--vscode-errorForeground);">Stop</button>
            </div>
            <script>
                const vscode = acquireVsCodeApi();
                let pendingFiles = [];
                let currentAbortController = null;
                let streamBuffer = ""; // ДЛЯ ЗАХИСТУ ВІД РОЗРИВУ JSON

                async function handleSend() {
                    const prompt = document.getElementById('prompt').value;
                    const intent = document.getElementById('intent').value;
                    const mode = document.getElementById('mode').value;
                    
                    document.getElementById('sendBtn').style.display = 'none';
                    document.getElementById('stopBtn').style.display = 'block';
                    
                    const chat = document.getElementById('chat');
                    chat.innerHTML += \`<div><b>You:</b> \${prompt}</div>\`;
                    
                    let aiDiv = document.createElement('div');
                    aiDiv.innerHTML = '<b>AI:</b> <span class="content"></span>';
                    chat.appendChild(aiDiv);
                    const contentTarget = aiDiv.querySelector('.content');

                    currentAbortController = new AbortController();
                    streamBuffer = ""; 

                    try {
                        const response = await fetch('http://localhost:8000/chat', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ 
                                query: prompt, 
                                context: { 
                                    intent: parseInt(intent), 
                                    mode, 
                                    attached_files: pendingFiles,
                                    workspace_path: "${workspacePath}" // ПРАВИЛЬНА ПЕРЕДАЧА ШЛЯХУ
                                } 
                            }),
                            signal: currentAbortController.signal
                        });

                        const reader = response.body.getReader();
                        const decoder = new TextDecoder();
                        let fullAiText = "";

                        while (true) {
                            const { value, done } = await reader.read();
                            if (done) break;

                            streamBuffer += decoder.decode(value, { stream: true });
                            let lines = streamBuffer.split('\\n');
                            streamBuffer = lines.pop(); // Залишаємо незавершений рядок у буфері

                            for (const line of lines) {
                                if (!line.trim()) continue;
                                try {
                                    const data = JSON.parse(line);
                                    if (data.type === 'chunk') {
                                        fullAiText += data.content;
                                        contentTarget.innerHTML = marked.parse(fullAiText);
                                    } else if (data.type === 'status') {
                                        document.getElementById('status').innerText = data.content;
                                    } else if (data.type === 'command_proposal') {
                                        renderCommand(data.command, aiDiv);
                                    }
                                } catch (e) { console.error("JSON Error", e); }
                            }
                            chat.scrollTop = chat.scrollHeight;
                        }
                    } catch (err) {
                        document.getElementById('status').innerText = "Error: " + err.message;
                    } finally {
                        document.getElementById('sendBtn').style.display = 'block';
                        document.getElementById('stopBtn').style.display = 'none';
                    }
                }

                function renderCommand(cmd, container) {
                    const box = document.createElement('div');
                    box.className = 'command-box';
                    box.innerHTML = \`<div>Run: <code>\${cmd}</code>?</div>
                        <button onclick="confirm(true, this)">Accept</button>
                        <button onclick="confirm(false, this)">Reject</button>\`;
                    container.appendChild(box);
                }

                window.confirm = (acc, btn) => {
                    vscode.postMessage({ type: acc ? 'executeCommand' : 'rejectCommand' });
                    btn.parentElement.innerHTML = acc ? "✅ Executed" : "❌ Rejected";
                };

                document.getElementById('sendBtn').onclick = handleSend;
                document.getElementById('stopBtn').onclick = () => currentAbortController.abort();
                document.getElementById('attachBtn').onclick = () => vscode.postMessage({ type: 'attachFile' });
                
                window.addEventListener('message', e => {
                    if (e.data.type === 'fileAttached') pendingFiles.push(e.data);
                    if (e.data.type === 'commandResult') {
                        chat.innerHTML += \`<pre>\${e.data.value}</pre>\`;
                    }
                });
            </script>
        </body>
        </html>`;
    }
}