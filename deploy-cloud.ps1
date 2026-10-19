# FORENSIGHT AI — one-shot cloud deployment (Render + Vercel).
#
# Everything this project needs for a public deployment is already committed:
# render.yaml, vercel.json, and the PostgreSQL/BYTEA backend. This script just
# drives the provider APIs so you do not have to click through dashboards.
#
# Prerequisites (run each ONCE in PowerShell):
#
#   render.com -> Account Settings -> API Keys -> Create API Key
#   $env:RENDER_API_KEY = "rnd_..."
#
#   Neon console -> Connection string -> POOLED, without &channel_binding=require
#   $env:DATABASE_URL = "postgresql://neondb_owner:.../neondb?sslmode=require"
#
#   vercel login
#
# Then:
#
#   powershell -ExecutionPolicy Bypass -File .\deploy-cloud.ps1
#
# Safe to re-run: it reuses an existing service instead of creating a duplicate.

$ErrorActionPreference = "Stop"

$Repo       = "https://github.com/methila-2056/forensight-ai"
$Branch     = "main"
$ServiceName= "foresight-api"
$RootDir    = "backend"

function Say($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# ---------------------------------------------------------------------------
# 0. Preflight
# ---------------------------------------------------------------------------
Say "Checking prerequisites"

$missing = @()
if (-not $env:RENDER_API_KEY) { $missing += "RENDER_API_KEY" }
if (-not $env:DATABASE_URL)  { $missing += "DATABASE_URL" }

foreach ($m in $missing) {
    Say "Missing $m"
    if ($m -eq "RENDER_API_KEY") {
        Write-Host "  Get one: render.com -> Account Settings -> API Keys -> Create API Key"
    } else {
        Write-Host "  Copy the POOLED connection string from the Neon console."
        Write-Host "  Remove '&channel_binding=require' from the end."
    }
}
if ($missing.Count) { Write-Host "`nNothing was deployed. Set the variables above and re-run." -ForegroundColor Red; exit 1 }

if ($env:DATABASE_URL -match "channel_binding") {
    Write-Host "`nDATABASE_URL still contains 'channel_binding', which fails against pooled" -ForegroundColor Red
    Write-Host "endpoints. Remove '&channel_binding=require' and re-run." -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# 1. Render — reuse the existing service if we already created one
# ---------------------------------------------------------------------------
$headers = @{
    Authorization = "Bearer $env:RENDER_API_KEY"
    "Content-Type" = "application/json"
    Accept         = "application/json"
}

Say "Looking for an existing Render service named '$ServiceName'"
$services = Invoke-RestMethod -Uri "https://api.render.com/v1/services?limit=100" -Headers $headers -Method Get
$existing = @($services | Where-Object { $_.service.name -eq $ServiceName })

if ($existing.Count -gt 0) {
    $svc      = $existing[0]
    $serviceId= $svc.id
    Say "Found existing service $serviceId - updating it instead of duplicating"
    $patchBody = @{
        envVars = @(
            @{ key = "DATABASE_URL";         value = $env:DATABASE_URL },
            @{ key = "EVIDENCE_STORAGE_BACKEND"; value = "database" },
            @{ key = "APP_NAME";             value = "FORENSIGHT AI" }
        )
    } | ConvertTo-Json -Depth 6
    Invoke-RestMethod -Uri "https://api.render.com/v1/services/$serviceId/env-vars" `
        -Headers $headers -Method Put -Body $patchBody | Out-Null
    Say "Environment variables updated"
} else {
    Say "Creating the Render service (this deploys commit $Branch)"
    $createBody = @{
        name            = $ServiceName
        repo            = $Repo
        branch          = $Branch
        runtime         = "python"
        plan            = "free"
        rootDir         = $RootDir
        buildCommand    = "pip install --no-cache-dir -r requirements.txt"
        startCommand    = "uvicorn app.main:app --host 0.0.0.0 --port `$PORT --workers 1"
        healthCheckPath = "/api/health"
        autoDeploy      = "true"
        envVars         = @(
            @{ key = "DATABASE_URL";             value = $env:DATABASE_URL },
            @{ key = "EVIDENCE_STORAGE_BACKEND"; value = "database" },
            @{ key = "APP_NAME";                 value = "FORENSIGHT AI" },
            @{ key = "APP_VERSION";              value = "0.1.0" },
            @{ key = "MAX_UPLOAD_MB";            value = "25" },
            @{ key = "ANOMALY_THRESHOLD";        value = "0.72" },
            @{ key = "RANDOM_STATE";             value = "42" },
            @{ key = "ANALYSIS_WINDOW_MINUTES";  value = "5" },
            @{ key = "ML_Z_SIGMAS";              value = "2.0" },
            @{ key = "ML_MIN_WINDOWS";           value = "8" }
        )
    } | ConvertTo-Json -Depth 6

    $created   = Invoke-RestMethod -Uri "https://api.render.com/v1/services" -Headers $headers -Method Post -Body $createBody
    $serviceId = $created.id
    Say "Created service $serviceId"
}

# ---------------------------------------------------------------------------
# 2. Wait for Render to go live
# ---------------------------------------------------------------------------
Say "Waiting for the deploy to finish (free tier can take 3-5 minutes)"
$renderUrl = $null
for ($i = 1; $i -le 60; $i++) {
    Start-Sleep -Seconds 15
    $s = Invoke-RestMethod -Uri "https://api.render.com/v1/services/$serviceId" -Headers $headers -Method Get
    $state = $s.serviceDetails.runtimeMetrics | Out-Null
    $name  = $s.service.name
    $url   = $s.service.serviceDetails.url
    $status = $s.service.updatedAt
    Write-Host ("  [{0,2}/60] {1}" -f $i, $url)
    if ($url) { $renderUrl = $url; break }
}
if (-not $renderUrl) { Write-Host "Render did not report a URL yet. Check the dashboard." -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
# 3. Vercel — deploy the frontend
# ---------------------------------------------------------------------------
Say "Deploying the frontend to Vercel"
Push-Location "$PSScriptRoot\frontend"

# The frontend calls the API through VITE_API_BASE, which must point at Render.
$env:VITE_API_BASE = $renderUrl
if (-not $renderUrl) { $env:VITE_API_BASE = "" ; Write-Host "  (no Render URL yet - set VITE_API_BASE manually and redeploy)" -ForegroundColor Yellow }

$vercelOut = & vercel deploy --prod --yes 2>&1 | Out-String
Pop-Location

$vercelUrl = ($vercelOut -split "`n" | Where-Object { $_ -match "https://[a-z0-9.-]+\.vercel\.app" } | Select-Object -Last 1)
if ($vercelUrl) { $vercelUrl = ($vercelUrl -replace "[^a-zA-Z0-9:/.-]", "") }

# ---------------------------------------------------------------------------
# 4. Close the CORS loop
# ---------------------------------------------------------------------------
if ($renderUrl -and $vercelUrl) {
    Say "Allowing the Vercel origin on Render"
    $corsBody = @{
        envVars = @(
            @{ key = "DATABASE_URL";             value = $env:DATABASE_URL },
            @{ key = "EVIDENCE_STORAGE_BACKEND"; value = "database" },
            @{ key = "CORS_ORIGINS";            value = $vercelUrl }
        )
    } | ConvertTo-Json -Depth 6
    Invoke-RestMethod -Uri "https://api.render.com/v1/services/$serviceId/env-vars" `
        -Headers $headers -Method Put -Body $corsBody | Out-Null
    Say "CORS_ORIGINS set to $vercelUrl (Render is restarting, ~60s)"
}

# ---------------------------------------------------------------------------
# 5. Report
# ---------------------------------------------------------------------------
Say "Deployment summary"
Write-Host ""
Write-Host "  Backend API : $renderUrl/api/health" -ForegroundColor Green
Write-Host "  API docs    : $renderUrl/docs" -ForegroundColor Green
Write-Host "  Frontend    : $vercelUrl" -ForegroundColor Green
Write-Host ""
Write-Host "Open the frontend URL, create a case, and upload evidence."
Write-Host "The free Render tier sleeps after 15 minutes idle, so the first"
Write-Host "request after a break takes up to ~30s while it wakes."