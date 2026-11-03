$ErrorActionPreference = 'Stop'
$arcRoot = Split-Path -Parent $PSScriptRoot
$arcState = Join-Path $arcRoot '.arc\terminal-runtime'
$arcEngine = Start-Process -FilePath "$env:SystemRoot\System32\wsl.exe" -ArgumentList @(
    '-d', 'ARC-Terminal', '-u', 'root', '--cd', '/', '--exec',
    '/usr/bin/env', '-i', 'PATH=/usr/sbin:/usr/bin:/sbin:/bin', 'HOME=/root',
    '/usr/bin/dockerd', '--bridge=none', '--iptables=false',
    '--ip-forward=false', '--ip-masq=false'
) -WorkingDirectory $arcRoot -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $arcState 'engine-out.log') `
  -RedirectStandardError (Join-Path $arcState 'engine-error.log')
@{engine = $arcEngine.Id} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $arcState 'engine-process.json')
Write-Output 'Started the private ARC container engine.'
