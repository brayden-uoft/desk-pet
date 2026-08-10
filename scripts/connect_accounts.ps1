param(
    [ValidateSet("all", "github", "google", "outlook", "microsoft", "notion", "slack", "dropbox", "status")]
    [string]$Provider = "all",
    [string]$GoogleClientJson = "",
    [string]$ClientId = "",
    [string]$Account = "",
    [ValidateSet("personal", "work", "work-teams")]
    [string]$MicrosoftAccountType = "",
    [switch]$Disconnect,
    [switch]$DryRun,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

Set-Location $RepoRoot
if (-not (Test-Path $Python)) {
    py -3.12 -m venv .venv
}
if (-not $SkipInstall) {
    & $Python -m pip install -e ".[desktop]" --quiet
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($GoogleClientJson -and -not $DryRun) {
    & $Python -m desk_pet.auth.wizard --import-google-client $GoogleClientJson
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Save-DeskBobClient {
    param([string]$Name, [string]$ClientId)
    $Arguments = @("-m", "desk_pet.auth.wizard", "--save-client", $Name, $ClientId)
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Could not save the $Name OAuth registration." }
}

if ($ClientId -and -not $DryRun) {
    if ($Provider -notin @("microsoft", "slack", "dropbox")) {
        throw "-ClientId is used only with -Provider microsoft, slack, or dropbox."
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
    if ($Status -match "microsoft(?::\S+)?\s+(connected|ready to sign in)") { return }

    $AzPath = "${env:ProgramFiles}\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
    $Az = Get-Command az -ErrorAction SilentlyContinue
    if (-not $Az -and (Test-Path $AzPath)) {
        $Az = @{ Source = $AzPath }
    }
    if (-not $Az) {
        Write-Host "`nInstalling the Microsoft Azure CLI (one time)..."
        winget install --id Microsoft.AzureCLI -e --accept-package-agreements --accept-source-agreements
        if (-not (Test-Path $AzPath)) {
            throw "Azure CLI installed, but this PowerShell session cannot find it. Reopen PowerShell and rerun this script."
        }
        $Az = @{ Source = $AzPath }
    }

    Write-Host "`nDeskBob first needs one Microsoft OAuth application registration."
    Write-Host "Sign in with an account that owns an Entra tenant and may create apps."
    Write-Host "This can be different from the Outlook account DeskBob will read afterward."
    & $Python -m desk_pet.auth.azure_cli --az $Az.Source
    if ($LASTEXITCODE -ne 0) {
        throw "Microsoft OAuth app registration was not completed."
    }
}

function Show-OutlookClassicStatus {
    Write-Host "`nDeskBob Outlook Classic setup"
    Write-Host "This uses the Outlook profile already on this PC. No Azure tenant, app registration, API key, billing, or trial is required."
    Write-Host "Open Outlook (classic), add every Outlook/Microsoft account you want DeskBob to read, and let initial mail sync finish."
    if ($DryRun) {
        Write-Host "DRY RUN: $Python -m desk_pet.integrations.outlook_classic --status"
        return
    }
    & $Python -m desk_pet.integrations.outlook_classic --status
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Outlook Classic is not ready. Open Outlook (classic), sign in there, then rerun this wizard."
        $script:OverallExitCode = 2
    }
}

if ($Provider -eq "status") {
    if ($Disconnect) { throw "-Disconnect requires a specific account provider." }
    & $Python -m desk_pet.auth.wizard --status
    $OAuthStatus = $LASTEXITCODE
    & $Python -m desk_pet.integrations.outlook_classic --status
    $OutlookStatus = $LASTEXITCODE
    if ($OAuthStatus -ne 0 -or $OutlookStatus -ne 0) { exit 2 }
    exit 0
}

if ($Disconnect) {
    if ($Provider -eq "all") {
        throw "-Disconnect requires one provider at a time."
    }
    if ($Provider -eq "outlook") {
        Write-Host "Outlook Classic has no DeskBob token to disconnect."
        Write-Host "Remove or sign out of the account in Outlook (classic) itself."
        exit 0
    }
    $DisconnectArguments = @("-m", "desk_pet.auth.wizard", "--disconnect", $Provider)
    if ($Account) { $DisconnectArguments += @("--account", $Account) }
    if ($DryRun) {
        Write-Host "DRY RUN: $Python $($DisconnectArguments -join ' ')"
        exit 0
    }
    & $Python @DisconnectArguments
    exit $LASTEXITCODE
}

[string[]]$Requested = @()
if ($Provider -eq "all") {
    $Requested = @("github", "outlook", "notion", "google", "slack", "dropbox")
} else {
    $Requested = @($Provider)
}

$OverallExitCode = 0
Write-Host "`nDeskBob free connector wizard"
Write-Host "The default paths use permanent free access or standard free quotas; this script never enables provider billing or starts a trial."
Write-Host "DeskBob's OpenAI API model/tool requests are still billed separately by OpenAI."
foreach ($RequestedProvider in $Requested) {
    if ($RequestedProvider -eq "outlook") {
        Show-OutlookClassicStatus
        continue
    }
    $ProviderAccount = if ($RequestedProvider -in @("google", "microsoft")) {
        $Account
    } else {
        ""
    }
    if ($RequestedProvider -in @("google", "microsoft") -and -not $ProviderAccount) {
        Write-Host "`nGive the $RequestedProvider login a short label so DeskBob can distinguish it."
        Write-Host "Examples: personal, uoft, work"
        $ProviderAccount = Read-Host "Account label"
        if (-not $ProviderAccount) {
            Write-Warning "Skipping $RequestedProvider because no account label was supplied."
            $OverallExitCode = 2
            continue
        }
    }

    if ($RequestedProvider -eq "microsoft") {
        if ($MicrosoftAccountType -eq "personal") {
            Write-Host "`nPersonal Outlook setup now uses Outlook Classic locally so it does not need Azure."
            Show-OutlookClassicStatus
            continue
        }
        if (-not $MicrosoftAccountType) {
            Write-Host "`nChoose the Microsoft permission profile:"
            Write-Host "  personal   - local Outlook Classic (free; no Azure)"
            Write-Host "  work       - Outlook plus SharePoint/OneDrive"
            Write-Host "  work-teams - Outlook, SharePoint/OneDrive, and Teams (admin may be required)"
            $MicrosoftAccountType = Read-Host "Profile"
            if ($MicrosoftAccountType -notin @("personal", "work", "work-teams")) {
                Write-Warning "Skipping Microsoft because the profile was invalid."
                $OverallExitCode = 2
                continue
            }
        }
        if ($MicrosoftAccountType -eq "personal") {
            Write-Host "`nPersonal Outlook setup uses Outlook Classic locally so it does not need Azure."
            Show-OutlookClassicStatus
            continue
        }
        try {
            if (-not $DryRun) { Initialize-MicrosoftOAuth }
        } catch {
            Write-Warning "Skipping Microsoft for this run: $($_.Exception.Message)"
            $OverallExitCode = 2
            continue
        }
    }

    Write-Host "`nDeskBob $RequestedProvider account setup"
    Write-Host "Only provider sign-in and consent pages will receive your passwords."
    $WizardArguments = @(
        "-m", "desk_pet.auth.wizard", $RequestedProvider, "--no-status"
    )
    if ($ProviderAccount) { $WizardArguments += @("--account", $ProviderAccount) }
    if ($RequestedProvider -eq "microsoft") {
        $WizardArguments += @("--microsoft-account-type", $MicrosoftAccountType)
    }
    if ($DryRun) {
        Write-Host "DRY RUN: $Python $($WizardArguments -join ' ')"
        continue
    }
    & $Python @WizardArguments
    if ($LASTEXITCODE -ne 0) { $OverallExitCode = 2 }
}

if (-not $DryRun) {
    & $Python -m desk_pet.auth.wizard --status
    & $Python -m desk_pet.integrations.outlook_classic --status
}
exit $OverallExitCode
