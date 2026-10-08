# Install git pre-push hook for AI log submission (Windows PowerShell).
# Run once after cloning: powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1

$ErrorActionPreference = 'Stop'

$HookFile = '.git/hooks/pre-push'

# Git on Windows runs hooks via Git Bash, so the hook body must be bash.
$HookBody = @'
#!/usr/bin/env python
"""Pre-push hook: sweep recent IDE prompts, then submit AI logs."""
import subprocess
import sys

commands = [
    [sys.executable, "scripts/log_antigravity.py", "--auto"],
    [sys.executable, "scripts/log_codex_extension.py", "--auto"],
    [sys.executable, "scripts/submit_log.py"],
]

for cmd in commands:
    try:
        subprocess.run(cmd, check=False)
    except Exception as exc:
        print(f"[ai-log] hook step failed: {exc}", file=sys.stderr)

sys.exit(0)
'@

$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText((Resolve-Path $HookFile), $HookBody, $Utf8NoBom)
Write-Host "[ai-log] Git pre-push hook installed."

if (-not (Test-Path .ai-log)) { New-Item -ItemType Directory -Path .ai-log | Out-Null }
if (-not (Test-Path .ai-log/.gitkeep)) { New-Item -ItemType File -Path .ai-log/.gitkeep | Out-Null }

Write-Host "[ai-log] Setup complete. Configure AI_LOG_SERVER in your .env file."
