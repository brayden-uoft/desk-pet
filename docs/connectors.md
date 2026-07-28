# External connectors

DeskBob supports browser-based OAuth, automatic token refresh, and secure
storage in Windows Credential Manager. Start the guided wizard from PowerShell:

```powershell
.\scripts\connect_accounts.ps1
```

The wizard installs its local dependencies, opens provider sign-in/consent
pages, and reports which accounts are connected. It never asks for an access
token and never prints saved credentials. Check status later with:

```powershell
.\scripts\connect_accounts.ps1 -Provider status
```

Restart DeskBob after connecting an account. GitHub reuses the GitHub CLI
login and routes through GitHub's server-enforced read-only MCP endpoint. One Google authorization enables
Gmail, Google Calendar, and Drive. One Microsoft authorization enables Outlook
Mail, Outlook Calendar, Teams, SharePoint, and OneDrive. Notion uses its
official hosted MCP server. Dropbox uses the OpenAI-maintained connector. Slack
uses Slack's official hosted MCP server.

## Multiple Google and Microsoft accounts

Run the wizard once per account. If `-Account` is omitted for an individual
Google or Microsoft setup, the script asks for a short label:

```powershell
.\scripts\connect_accounts.ps1 -Provider google -Account personal
.\scripts\connect_accounts.ps1 -Provider google -Account uoft
.\scripts\connect_accounts.ps1 -Provider microsoft -Account personal
.\scripts\connect_accounts.ps1 -Provider microsoft -Account uoft
```

The OAuth application registration is reused, but each login gets an
independent encrypted access/refresh-token session. Status shows every account:

```powershell
.\scripts\connect_accounts.ps1 -Provider status
```

DeskBob exposes account-qualified tools such as `gmail_personal`,
`gmail_uoft`, `outlook_calendar_personal`, and `outlook_calendar_uoft`. The
account label is also included in each tool description so DeskBob can choose
the right account or search both.

Only explicitly listed read operations are exposed. DeskBob cannot send mail,
change calendar events, post Slack messages, edit documents, move files, or
delete anything in this stage.

## Provider restrictions

OAuth providers require DeskBob to identify itself as an application before
they let a user sign in:

- **Microsoft:** the script installs Azure CLI if needed, opens Microsoft
  sign-in, and attempts to register the local public client automatically.
  University tenants can block user-created apps or require administrator
  consent for Teams/SharePoint scopes. The script disables Azure CLI's Windows
  authentication broker and subscription selector before login because those
  paths can fail for accounts without an Azure subscription. If browser login
  still fails, it automatically retries with Microsoft's device-code flow.
  When Microsoft setup fails during the full wizard, the other providers
  continue instead of being abandoned.
- **Notion:** supports dynamic client registration, so its flow is fully
  automatic apart from sign-in and consent.
- **GitHub:** reuses `gh auth`; no app registration or copied token is needed.
- **Google:** Google does not provide a supported CLI/API for creating a normal
  desktop OAuth client. Create a Desktop app client once, download its JSON,
  then run `.\scripts\connect_accounts.ps1 -GoogleClientJson .\client.json`.
  The JSON is imported into Windows Credential Manager and does not belong in
  the repository.
- **Slack:** Slack requires a registered internal or Marketplace app and does
  not support dynamic client registration. Its registered redirect URL must be
  `http://localhost:53682`. After its client ID/secret are saved, the normal
  browser consent flow can run:

  ```powershell
  .\scripts\connect_accounts.ps1 -Provider slack -ClientId YOUR_ID
  ```

- **Dropbox:** Dropbox requires an app registration/app key with redirect URI
  `http://localhost:53683`. After its client ID is saved once, authentication
  is browser-only:

  ```powershell
  .\scripts\connect_accounts.ps1 -Provider dropbox -ClientId YOUR_APP_KEY
  ```

These are provider-enforced app-registration requirements, not API-key
collection. Access and refresh tokens remain local and encrypted by Windows.
Existing ChatGPT/Codex connector sessions cannot be exported into a standalone
Python application.

Legacy `DESKBOB_*_OAUTH_TOKEN` variables in `.env` still work for development,
but they expire and are not the recommended setup.
