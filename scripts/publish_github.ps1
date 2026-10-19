#Requires -Version 5.1
<#
.SYNOPSIS
    Create the first Git commit of this folder and push it to an empty GitHub repo.
.DESCRIPTION
    Run this after creating an empty repository on GitHub (no README, no .gitignore).
    The script never stores credentials: Git asks for them, or uses your existing
    Windows credential manager entry.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\publish_github.ps1 `
        -RepoUrl https://github.com/Dream-Alan/Piano_Waterfall_Layout.git

.EXAMPLE
    # Optional: also tag v1.1.0, which triggers the release workflow on GitHub.
    powershell -ExecutionPolicy Bypass -File scripts\publish_github.ps1 `
        -RepoUrl git@github.com:Dream-Alan/Piano_Waterfall_Layout.git -Tag v1.3.0
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoUrl,
    [string]$Branch = "main",
    [string]$Message = "Piano Waterfall 1.3.0",
    [string]$Tag = "",
    [string]$UserName = "",
    [string]$UserEmail = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$git = "git"
if (Test-Path "C:\Program Files\Git\cmd\git.exe") {
    $git = "C:\Program Files\Git\cmd\git.exe"
}

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & $git @Args
    if ($LASTEXITCODE -ne 0) { throw "git $($Args -join ' ') failed with exit code $LASTEXITCODE" }
}

if (-not (Test-Path ".git")) {
    Write-Host "==> Initialising repository on branch $Branch" -ForegroundColor Cyan
    Invoke-Git init -b $Branch
}

$identity = @()
if ($UserName) { $identity += @("-c", "user.name=$UserName") }
if ($UserEmail) { $identity += @("-c", "user.email=$UserEmail") }

$remotes = & $git remote
if ($remotes -contains "origin") {
    Invoke-Git remote set-url origin $RepoUrl
} else {
    Invoke-Git remote add origin $RepoUrl
}

Invoke-Git add --all

$pending = & $git status --porcelain
if ($pending) {
    Write-Host "==> Committing" -ForegroundColor Cyan
    Invoke-Git @identity commit -m $Message
} else {
    Write-Host "==> Nothing to commit" -ForegroundColor Yellow
}

Write-Host "==> Pushing $Branch to $RepoUrl" -ForegroundColor Cyan
Invoke-Git push -u origin $Branch

if ($Tag) {
    Write-Host "==> Tagging $Tag" -ForegroundColor Cyan
    Invoke-Git @identity tag -a $Tag -m $Tag
    Invoke-Git push origin $Tag
    Write-Host "The release workflow will now build the Windows zip." -ForegroundColor Green
}

Write-Host "Done: $RepoUrl" -ForegroundColor Green
