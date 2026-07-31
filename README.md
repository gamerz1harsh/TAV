# Riverton — Year One

A native Windows desktop prototype of a choice-driven life simulation. It runs
entirely on your computer and saves the current game in `data/save_state.json`.

## Included in V1

- Four origins that alter stats and starting connections
- One modern Riverton neighborhood: apartment, Juniper Cafe, and community college
- Six named NPCs with affinity and trust scores
- Four seasonal main decisions and ten weighted, conditional random events
- Professional, community-leadership, cafe, and independent end-of-year paths
- Four player stats: energy, money, skill, and reputation

## Run the native app

From this folder in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

This opens Riverton in its own desktop window. Stop it by closing the window.

If PowerShell prevents activation, run this once for the current terminal, then repeat the activation command:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
