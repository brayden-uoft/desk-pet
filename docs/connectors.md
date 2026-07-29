# External connectors

DeskBob supports local Outlook Classic access plus browser-based OAuth,
automatic token refresh, and secure storage in Windows Credential Manager.
Start the guided wizard from PowerShell:

```powershell
.\scripts\connect_accounts.ps1
```

The default wizard never enables provider billing or starts a trial. It uses
permanent free access or each provider's standard free quotas. OpenAI API
model and hosted-tool requests are still billed separately by OpenAI.

The wizard installs local dependencies, opens provider sign-in/consent pages,
and reports which accounts are connected. It never asks for an access token
and never prints saved credentials. Check status later with:

```powershell
.\scripts\connect_accounts.ps1 -Provider status
```

Restart DeskBob after connecting an account. GitHub reuses the GitHub CLI
login and routes through GitHub's server-enforced read-only MCP endpoint. One
Google authorization enables Gmail, Google Calendar, and Drive. Personal
Microsoft mail and calendars are read locally from Outlook Classic, with no
Azure tenant or OAuth application. Notion uses its official hosted MCP server.
Dropbox uses the OpenAI-maintained connector. Slack uses Slack's official
hosted MCP server.

## Personal Outlook and multiple accounts

Open **Outlook (classic)** and add every Outlook/Hotmail/Microsoft account you
want DeskBob to read. Let Outlook finish its initial sync, then run:

```powershell
.\scripts\connect_accounts.ps1 -Provider outlook
```

DeskBob detects every configured Outlook store and exposes read-only
`search_outlook_mail` and `read_outlook_calendar` tools. It cannot send mail,
modify an event, or delete anything. The integration is local to this Windows
computer and requires no Azure subscription, trial, API key, copied token, or
app registration.

## Multiple Google accounts

Run the wizard once per Google account. If `-Account` is omitted, the script
asks for a short label:

```powershell
.\scripts\connect_accounts.ps1 -Provider google -Account personal
.\scripts\connect_accounts.ps1 -Provider google -Account uoft
```

The OAuth application registration is reused, but each login gets an
independent encrypted access/refresh-token session. Status shows every account:

```powershell
.\scripts\connect_accounts.ps1 -Provider status
```

DeskBob exposes account-qualified tools such as `gmail_personal` and
`gmail_uoft`. Local Outlook results include their Outlook store/account name so
DeskBob can distinguish accounts.

Disconnect a wrong or revoked login before reconnecting it:

```powershell
.\scripts\connect_accounts.ps1 -Provider google -Account personal -Disconnect
```

Only explicitly listed read operations are exposed. DeskBob cannot send mail,
change calendar events, post Slack messages, edit documents, move files, or
delete anything in this stage.

## Free-access boundaries and provider restrictions

OAuth providers require DeskBob to identify itself as an application before
they let a user sign in:

- **Outlook Classic:** local access through your existing Outlook desktop
  profile is included in the default flow and has no connector fee or trial.
- **Microsoft Graph (optional):** this is no longer part of the default setup.
  Use it only when a work/school organization supplies or permits an Entra
  application. It is still available explicitly for SharePoint, OneDrive, or
  Teams:

  ```powershell
  .\scripts\connect_accounts.ps1 -Provider microsoft -Account uoft -MicrosoftAccountType work -ClientId APPLICATION_ID
  ```

- **Notion:** its API is available to all users and supports dynamic client
  registration, so its flow is fully automatic apart from sign-in and consent.
- **GitHub:** reuses `gh auth`; no app registration or copied token is needed.
  Normal account/API limits still apply.
- **Google:** Google does not provide a supported CLI/API for creating a normal
  desktop OAuth client. Create a Desktop app client once, download its JSON,
  then run `.\scripts\connect_accounts.ps1 -GoogleClientJson .\client.json`.
  The JSON is imported into Windows Credential Manager and does not belong in
  the repository. Google OAuth apps left in external `Testing` status can issue
  refresh tokens that expire after seven days; publish the consent screen for
  durable personal use. Standard Workspace API quotas do not require enabling
  billing; DeskBob never requests quota overages.
- **Slack:** Slack requires a registered internal or Marketplace app and does
  not support dynamic client registration. Its registered redirect URL must be
  `http://localhost:53682`. Slack's Free plan is permanent but limits message
  history and installed apps. DeskBob does not use Slack's paid hosted
  workflow-app feature. After its client ID/secret are saved, the normal browser
  consent flow can run:

  ```powershell
  .\scripts\connect_accounts.ps1 -Provider slack -ClientId YOUR_ID
  ```

- **Dropbox:** Dropbox states that its API can be used for free with a free or
  paid Dropbox account. It requires an app registration/app key with redirect
  URI `http://localhost:53683`. After its client ID is saved once,
  authentication is browser-only:

  ```powershell
  .\scripts\connect_accounts.ps1 -Provider dropbox -ClientId YOUR_APP_KEY
  ```

These are provider-enforced app-registration requirements, not API-key
collection. Access and refresh tokens remain local and encrypted by Windows.
Existing ChatGPT/Codex connector sessions cannot be exported into a standalone
Python application.

Legacy `DESKBOB_*_OAUTH_TOKEN` variables in `.env` still work for development,
but they expire and are not the recommended setup.
