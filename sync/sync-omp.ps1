param(
    [string]$Remote = "devbox",
    [string]$OmpHome = "$HOME\.omp"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $OmpHome -PathType Container)) {
    throw "OMP directory not found: $OmpHome"
}

foreach ($cmd in @("tar", "ssh", "scp")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "$cmd is required. Windows 10/11 normally includes OpenSSH and bsdtar; otherwise run the bash script from WSL."
    }
}

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("omp-sync-" + [guid]::NewGuid().ToString("N") + ".tar.gz")
$remoteTmp = "/tmp/omp-sync-$env:USERNAME-$PID.tar.gz"
$parent = Split-Path -Parent $OmpHome
$base = Split-Path -Leaf $OmpHome

try {
    & tar -czf $tmp `
        "--exclude=*/agent.db" `
        "--exclude=*/agent.db-*" `
        "--exclude=*/.env" `
        "--exclude=*/sessions" `
        "--exclude=*/blobs" `
        "--exclude=*/logs" `
        "--exclude=*/auth-broker.token" `
        "--exclude=*/auth-gateway.token" `
        "--exclude=*/node_modules" `
        -C $parent $base
    if ($LASTEXITCODE -ne 0) { throw "tar failed" }

    Write-Host "Uploading sanitized OMP config to $Remote..."
    & scp $tmp "${Remote}:${remoteTmp}"
    if ($LASTEXITCODE -ne 0) { throw "scp failed" }

    & ssh $Remote "omp-sync-import '$remoteTmp'; rm -f '$remoteTmp'"
    if ($LASTEXITCODE -ne 0) { throw "remote import failed" }

    Write-Host "Done."
}
finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
}
