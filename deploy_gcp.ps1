# EventEase Google Cloud Run Deployment Script
param (
    [string]$ProjectId = "prism-sbi",
    [string]$Region = "asia-south1",
    [string]$DatabaseUrl = "",
    [string]$AdminKey = "secret"
)

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "   EventEase Google Cloud Platform (Cloud Run) Deploy" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# 1. Set active project
Write-Host "`n[1/4] Setting active GCP project to '$ProjectId'..." -ForegroundColor Yellow
gcloud config set project $ProjectId

# 2. Check Database URL
if (-not $DatabaseUrl) {
    Write-Host "`nEnter your PostgreSQL Database Connection String:" -ForegroundColor Green
    Write-Host "(e.g., from Neon.tech: postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require)" -ForegroundColor Gray
    $DatabaseUrl = Read-Host "DATABASE_URL"
}

if (-not $DatabaseUrl) {
    Write-Host "`n[ERROR] DATABASE_URL is required for Cloud Run multi-instance load balancing." -ForegroundColor Red
    Write-Host "Get a free database in 30 seconds at https://neon.tech" -ForegroundColor Yellow
    exit 1
}

# 3. Enable Cloud Run & Cloud Build APIs
Write-Host "`n[2/4] Enabling Cloud Run, Cloud Build, and Artifact Registry APIs..." -ForegroundColor Yellow
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[ERROR] Failed to enable GCP services. Make sure billing is active on project '$ProjectId':" -ForegroundColor Red
    Write-Host "https://console.cloud.google.com/billing/linkedaccount?project=$ProjectId" -ForegroundColor Cyan
    exit 1
}

# 4. Deploy to Cloud Run with 2-3 instances for Load Balancing and HTTPS
Write-Host "`n[3/4] Building container and deploying to Cloud Run..." -ForegroundColor Yellow
Write-Host "Region: $Region | Min Instances: 2 | Max Instances: 3 (Active Load Balancing)" -ForegroundColor Gray

gcloud run deploy eventease `
    --source . `
    --region $Region `
    --allow-unauthenticated `
    --min-instances 2 `
    --max-instances 3 `
    --set-env-vars ENV=production,DATABASE_URL="$DatabaseUrl",ADMIN_KEY="$AdminKey"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=====================================================" -ForegroundColor Green
    Write-Host "   DEPLOYMENT SUCCESSFUL!" -ForegroundColor Green
    Write-Host "=====================================================" -ForegroundColor Green
    Write-Host "Your live HTTPS URL is printed above."
    Write-Host "Features enabled on GCP:"
    Write-Host "  * HTTPS: Google-managed TLS certificate with automatic HTTP->HTTPS redirect"
    Write-Host "  * Load Balancing: Google Front End balancing across 2-3 container instances"
    Write-Host "  * Rate Limiting: SlowAPI per-client-IP throttling returning HTTP 429"
    Write-Host "  * Database: Shared PostgreSQL with row-level locks"
}
