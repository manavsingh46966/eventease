# EventEase Cloud Run Deployer for project-dceff5eb-77af-4090-bbb
param (
    [string]$ProjectId = "project-dceff5eb-77af-4090-bbb",
    [string]$Region = "asia-south1",
    [string]$DatabaseUrl = "postgresql://neondb_owner:npg_XItPTRW76reE@ep-icy-king-b5gp9r5w-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
    [string]$AdminKey = "secret"
)

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "   Deploying EventEase to Google Cloud Project: $ProjectId" -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan

# 1. Set active project
Write-Host "`n[1/3] Setting active project to '$ProjectId'..." -ForegroundColor Yellow
gcloud config set project $ProjectId

# 2. Enable APIs
Write-Host "`n[2/3] Enabling Cloud Run and Cloud Build APIs on $ProjectId..." -ForegroundColor Yellow
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[!] Billing is not open yet on your GCP account." -ForegroundColor Red
    Write-Host "Please click 'Activate' or 'Make a payment' at:" -ForegroundColor Yellow
    Write-Host "https://console.cloud.google.com/billing" -ForegroundColor Cyan
    exit 1
}

# 3. Deploy to Cloud Run
Write-Host "`n[3/3] Deploying load-balanced container to Cloud Run (min 2, max 3 instances)..." -ForegroundColor Yellow
gcloud run deploy eventease `
    --source . `
    --region $Region `
    --allow-unauthenticated `
    --min-instances 2 `
    --max-instances 3 `
    --set-env-vars ENV=production,DATABASE_URL="$DatabaseUrl",ADMIN_KEY="$AdminKey"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=========================================================" -ForegroundColor Green
    Write-Host "   SUCCESS! YOUR LIVE LINK IS PRINTED ABOVE!" -ForegroundColor Green
    Write-Host "=========================================================" -ForegroundColor Green
}
