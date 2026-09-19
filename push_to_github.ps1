# Script to push portfolio1 to GitHub (digant2207/portfolio1)
Write-Host "Pushing code to https://github.com/digant2207/portfolio1.git..." -ForegroundColor Cyan
git branch -M main
git push -u origin main
if ($LASTEXITCODE -eq 0) {
    Write-Host "`nSUCCESS! Your project is now live on GitHub." -ForegroundColor Green
    Write-Host "Next step: Add your GMAIL_USER and GMAIL_APP_PASSWORD in:" -ForegroundColor Yellow
    Write-Host "https://github.com/digant2207/portfolio1/settings/secrets/actions" -ForegroundColor Yellow
} else {
    Write-Host "`nPush failed. Please make sure you have created the empty repository on GitHub first:" -ForegroundColor Red
    Write-Host "https://github.com/new?name=portfolio1&private=true" -ForegroundColor Red
}
