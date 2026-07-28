param(
    [ValidateSet("all", "github", "google", "microsoft", "notion", "slack", "dropbox", "status")]
    [string]$Provider = "all",
    [string]$GoogleClientJson = "",
    [string]$ClientId = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

Set-Location $RepoRoot
if (-not (Test-Path $Python)) {
    py -3.12 -m venv .venv
}
& $Python -m pip install -e ".[desktop]" --quiet

if ($GoogleClientJson) {
    & $Python -m desk_pet.auth.wizard --import-google-client $GoogleClientJson
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Save-DeskBobClient {
    param([string]$Name, [string]$ClientId)
    $Arguments = @("-m", "desk_pet.auth.wizard", "--save-client", $Name, $ClientId)
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Could not save the $Name OAuth registration." }
}

if ($ClientId) {
    if ($Provider -notin @("slack", "dropbox")) {
        throw "-ClientId is used only with -Provider slack or dropbox."
    }
    if ($Provider -eq "slack") {
        $SecureSecret = Read-Host "Slack client secret" -AsSecureString
        $SecretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureSecret)
        try {
            $env:DESKBOB_WIZARD_CLIENT_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($SecretPointer)
            Save-DeskBobClient $Provider $ClientId
        } finally {
            Remove-Item Env:DESKBOB_WIZARD_CLIENT_SECRET -ErrorAction SilentlyContinue
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($SecretPointer)
        }
    } else {
        Save-DeskBobClient $Provider $ClientId
    }
}

function Initialize-MicrosoftOAuth {
    $Status = & $Python -m desk_pet.auth.wizard --status
    if ($Status -match "microsoft\s+(connected|ready to sign in)") { return }

    $Az = Get-Command az -ErrorAction SilentlyContinue
    if (-not $Az) {
        Write-Host "`nInstalling the Microsoft Azure CLI (one time)..."
        winget install --id Microsoft.AzureCLI -e --accept-package-agreements --accept-source-agreements
        $AzPath = "${env:ProgramFiles}\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
        if (-not (Test-Path $AzPath)) {
            throw "Azure CLI installed, but this PowerShell session cannot find it. Reopen PowerShell and rerun this script."
        }
        $Az = @{ Source = $AzPath }
    }

    Write-Host "`nA Microsoft sign-in page will open. Sign in to the account DeskBob should read."
    & $Az.Source login --allow-no-subscriptions
    if ($LASTEXITCODE -ne 0) { throw "Microsoft sign-in was not completed." }
    $ClientId = & $Az.Source ad app create `
        --display-name "DeskBob Local" `
        --sign-in-audience AzureADandPersonalMicrosoftAccount `
        --is-fallback-public-client true `
        --public-client-redirect-uris "http://localhost" `
        --query appId -o tsv
    if ($LASTEXITCODE -ne 0 -or -not $ClientId) {
        throw "Your Microsoft tenant blocked automatic app registration. A tenant admin must allow user app registrations."
    }
    Save-DeskBobClient "microsoft" $ClientId.Trim()
}

if ($Provider -eq "status") {
    & $Python -m desk_pet.auth.wizard --status
    exit $LASTEXITCODE
}

[string[]]$Requested = @()
if ($Provider -eq "all") {
    $Requested = @("github", "microsoft", "notion", "google", "slack", "dropbox")
} else {
    $Requested = @($Provider)
}

if ($Requested -contains "microsoft") {
    Initialize-MicrosoftOAuth
}

Write-Host "`nDeskBob account connector wizard"
Write-Host "Only provider sign-in and consent pages will receive your passwords."
& $Python -m desk_pet.auth.wizard @Requested
exit $LASTEXITCODE
