Clear-Host

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    ГАЗЕТНЫЙ ЧАНКЕР v7.0" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Создаем папки
Write-Host "Создание рабочих папок..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "D:\ПП\ИРЗ\raw" | Out-Null
New-Item -ItemType Directory -Force -Path "D:\ПП\ИРЗ\Documents" | Out-Null
Write-Host "✓ Папки готовы" -ForegroundColor Green
Write-Host ""

# Проверяем Docker
Write-Host "Проверка Docker..." -ForegroundColor Yellow
$dockerVersion = docker --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Docker не найден! Установите Docker Desktop" -ForegroundColor Red
    exit 1
}
Write-Host "✓ $dockerVersion" -ForegroundColor Green

# Проверяем Python
Write-Host "Проверка Python..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Python не найден!" -ForegroundColor Red
    exit 1
}
Write-Host "✓ $pythonVersion" -ForegroundColor Green
Write-Host ""

# Запускаем обработку
Write-Host "Запуск обработки..." -ForegroundColor Cyan
Write-Host ""

python chunk_processor.py

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "ГОТОВО! Результаты: D:\ПП\ИРЗ\Documents" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Green