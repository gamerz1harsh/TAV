// Electron main process — manages the Python Flask API backend and the native window.
const { app, BrowserWindow, dialog, shell, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');

// ── Chromium network workarounds (must run before app is ready) ─────────────
// The web UI is served from the local Flask backend at 127.0.0.1:5500. On
// Windows, Chromium's Private Network Access (RFC1918) and CORS enforcement
// can block these localhost requests, surfacing as ERR_NETWORK_ACCESS_DENIED /
// CORS-RFC1918 errors. Disable those checks so the app can load its own UI.
app.commandLine.appendSwitch('disable-features', 'BlockInsecurePrivateNetworkRequests,OutOfBlinkCors,PrivateNetworkAccessSendPreflights');
app.commandLine.appendSwitch('disable-site-isolation-trials');
// Software rendering: prevents GPU/compositor crash-reload loops on Windows
// (especially in VMs/remote sessions) that manifest as an endlessly reloading,
// stuck blank window.
app.disableHardwareAcceleration();
app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-gpu-compositing');

// ── Configuration ──────────────────────────────────────────────────────────
const PROJECT_ROOT = path.resolve(__dirname, '..');
const API_DIR = path.join(PROJECT_ROOT, 'api');
const API_SCRIPT = path.join(API_DIR, 'server.py');
const API_HOST = '127.0.0.1';
const API_PORT = 5500; // Use a different port to avoid conflicts with standalone Flask
const HEALTH_URL = `http://${API_HOST}:${API_PORT}/api/health`;
const BASE_URL = `http://${API_HOST}:${API_PORT}`;
const STARTUP_TIMEOUT_MS = 30000;

// ── State ──────────────────────────────────────────────────────────────────
let mainWindow = null;
let pythonProcess = null;
let pythonReady = false;
let serverError = null;
// Single navigation entry point. loadURL must be called only once at startup;
// calling it again while a page is loaded re-fires 'ready-to-show', which in
// turn used to call loadURL again -> infinite reload loop.
function loadMainPage() {
  if (mainWindow && !mainWindow.webContents.isLoadingMainFrame()) {
    mainWindow.loadURL(BASE_URL);
  }
}

// ── Python discovery ───────────────────────────────────────────────────────
function findPython() {
  // Honor explicit override
  if (process.env.RIVERTON_PYTHON) {
    return process.env.RIVERTON_PYTHON;
  }
  // Look for venv python
  const venvPythonWin = path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe');
  const venvPythonUnix = path.join(PROJECT_ROOT, '.venv', 'bin', 'python');
  if (fs.existsSync(venvPythonWin)) return venvPythonWin;
  if (fs.existsSync(venvPythonUnix)) return venvPythonUnix;
  // Fall back to PATH
  return process.platform === 'win32' ? 'python.exe' : 'python3';
}

// ── Server health check ────────────────────────────────────────────────────
function checkHealth(retries = 60, interval = 500) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const tryCheck = () => {
      const req = http.get(HEALTH_URL, { timeout: 2000 }, (res) => {
        let body = '';
        res.on('data', (chunk) => { body += chunk; });
        res.on('end', () => {
          if (res.statusCode === 200) {
            try {
              const data = JSON.parse(body);
              if (data.status === 'ok') {
                resolve(data);
                return;
              }
            } catch (e) {}
          }
          attempts++;
          if (attempts < retries) { setTimeout(tryCheck, interval); }
          else { reject(new Error(`Health check failed (status ${res.statusCode})`)); }
        });
      });
      req.on('error', () => {
        attempts++;
        if (attempts < retries) { setTimeout(tryCheck, interval); }
        else { reject(new Error('Could not connect to Python server')); }
      });
      req.on('timeout', () => {
        req.destroy();
        attempts++;
        if (attempts < retries) { setTimeout(tryCheck, interval); }
        else { reject(new Error('Connection to Python server timed out')); }
      });
    };
    tryCheck();
  });
}

// ── Start Python server ────────────────────────────────────────────────────
function startPythonServer() {
  const pythonExe = findPython();
  const env = {
    ...process.env,
    RIVERTON_PORT: String(API_PORT),
    RIVERTON_HOST: API_HOST,
    PYTHONUNBUFFERED: '1',
    PYTHONDONTWRITEBYTECODE: '1',
  };

  console.log(`[Electron] Starting Python server with: ${pythonExe} ${API_SCRIPT}`);
  pythonProcess = spawn(pythonExe, [API_SCRIPT], {
    cwd: PROJECT_ROOT,
    env,
    windowsHide: true,
  });

  pythonProcess.stdout.on('data', (data) => {
    const text = data.toString().trim();
    if (text) console.log(`[Python] ${text}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    const text = data.toString().trim();
    if (text) console.error(`[Python ERR] ${text}`);
  });

  pythonProcess.on('exit', (code, signal) => {
    if (code !== 0 && !signal) {
      console.log(`[Python] Process exited with code ${code}`);
    }
    if (pythonReady && pythonProcess && code !== 0) {
      serverError = `Server exited unexpectedly (code ${code})`;
    }
    pythonProcess = null;
  });

  return pythonProcess;
}

// ── Window creation ────────────────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    show: false, // Don't show until server is ready
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: false,
      devTools: process.env.NODE_ENV === 'development',
    },
    title: 'Anime Sim',
    titleBarStyle: 'default',
    icon: path.join(PROJECT_ROOT, 'web', 'icon.png'),
  });

  // Diagnostics: surface renderer console, errors, and crash events.
  mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
    console.log(`[Renderer:${level}] ${message} (${sourceId}:${line})`);
  });
  mainWindow.webContents.on('render-process-gone', (event, details) => {
    console.error('[Electron] Renderer process gone:', JSON.stringify(details));
  });
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL) => {
    console.error('[Electron] did-fail-load:', errorCode, errorDescription, validatedURL);
  });

  // Handle external links
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  mainWindow.on('ready-to-show', () => {
    // show() only. Do NOT call loadURL here: doing so starts a navigation that
    // itself re-fires 'ready-to-show', causing an infinite reload loop.
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── Server readiness flow ──────────────────────────────────────────────────
async function waitForServerThenShow() {
  const timeout = setTimeout(() => {
    serverError = `Server did not become ready within ${STARTUP_TIMEOUT_MS / 1000}s`;
    console.error('[Electron] Server did not become ready within timeout');
    if (mainWindow) {
      mainWindow.webContents.send('server:failed', serverError);
      mainWindow.loadFile(path.join(PROJECT_ROOT, 'web', 'loading.html'), {
        queryParams: { error: serverError }
      });
      mainWindow.show();
    }
  }, STARTUP_TIMEOUT_MS);

  try {
    const health = await checkHealth();
    pythonReady = true;
    clearTimeout(timeout);
    console.log('[Electron] Python server is ready:', health);
    if (mainWindow) {
      mainWindow.webContents.send('server:ready');
      mainWindow.show();
      loadMainPage();
    }
  } catch (err) {
    clearTimeout(timeout);
    serverError = err.message;
    console.error('[Electron] Server failed to start:', err.message);
    if (mainWindow) {
      mainWindow.webContents.send('server:failed', serverError);
      mainWindow.loadFile(path.join(PROJECT_ROOT, 'web', 'loading.html'), {
        queryParams: { error: serverError }
      });
      mainWindow.show();
    }
  }
}

// ── IPC handlers ───────────────────────────────────────────────────────────
ipcMain.handle('python:info', () => ({
  pythonPath: findPython(),
  apiUrl: BASE_URL,
  port: API_PORT,
}));

ipcMain.handle('dialog:error', async (_event, title, content) => {
  if (mainWindow) {
    return dialog.showMessageBox(mainWindow, {
      type: 'error',
      title,
      message: content,
      buttons: ['OK'],
    });
  }
});

ipcMain.handle('shell:openExternal', async (_event, url) => {
  return shell.openExternal(url);
});

ipcMain.on('app:log', (_event, level, message) => {
  console.log(`[Renderer ${level}] ${message}`);
});

// ── App lifecycle ─────────────────────────────────────────────────────────
function shutdownPython() {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
}

app.whenReady().then(() => {
  startPythonServer();
  createWindow();
  waitForServerThenShow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('before-quit', () => {
  shutdownPython();
});

app.on('window-all-closed', () => {
  shutdownPython();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
