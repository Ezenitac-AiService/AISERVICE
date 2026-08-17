# init_network.ps1: aiservice-network Docker network initialization script
$NetworkName = "aiservice-network"

Write-Host "Checking Docker network: $NetworkName..." -ForegroundColor Cyan

$existing = docker network ls --filter name=^${NetworkName}$ --format "{{.Name}}"

if ($existing -eq $NetworkName) {
    Write-Host "Docker network '$NetworkName' already exists." -ForegroundColor Green
} else {
    Write-Host "Creating Docker network '$NetworkName'..." -ForegroundColor Yellow
    docker network create $NetworkName
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Successfully created Docker network '$NetworkName'." -ForegroundColor Green
    } else {
        Write-Error "Failed to create Docker network '$NetworkName'."
        exit $LASTEXITCODE
    }
}
