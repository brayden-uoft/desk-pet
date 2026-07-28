# External connectors

DeskBob can attach OpenAI-maintained connectors to every Responses API request.
A connector is enabled only when its OAuth access token is present in the local
`.env` file. Tokens are sent with each request but are never committed, logged,
stored in conversation history, or returned in the API response.

## Supported services

| Service | Environment variable | Access exposed to DeskBob |
| --- | --- | --- |
| Gmail | `DESKBOB_GMAIL_OAUTH_TOKEN` | Search and read mail |
| Google Calendar | `DESKBOB_GOOGLE_CALENDAR_OAUTH_TOKEN` | Search and read events |
| Google Drive | `DESKBOB_GOOGLE_DRIVE_OAUTH_TOKEN` | Search and read files |
| Outlook Calendar | `DESKBOB_OUTLOOK_CALENDAR_OAUTH_TOKEN` | Search and read events |
| Outlook Email | `DESKBOB_OUTLOOK_EMAIL_OAUTH_TOKEN` | Search and read mail |
| Microsoft Teams | `DESKBOB_MICROSOFT_TEAMS_OAUTH_TOKEN` | Search and read messages |
| SharePoint/OneDrive | `DESKBOB_SHAREPOINT_OAUTH_TOKEN` | Search and read documents |
| Dropbox | `DESKBOB_DROPBOX_OAUTH_TOKEN` | Search and read files |

Only explicitly enumerated read operations are exposed. Sending email, changing
calendar events, editing documents, moving files, and deleting anything are not
available in this stage.

## First acceptance test: Google Calendar

The initial connector demo uses a temporary OAuth access token. Generate a
Google token with the Calendar Events scope, then add it only to `.env`:

```dotenv
DESKBOB_GOOGLE_CALENDAR_OAUTH_TOKEN=your-temporary-access-token
```

Restart DeskBob and ask:

> What is on my calendar today, and does anything affect what I should wear?

DeskBob should use the calendar connector and web weather search, then give one
combined answer. Remove the token from `.env` to disconnect the calendar.

Temporary access tokens expire. A later connector-auth stage will add a local
OAuth broker with refresh-token storage in the Windows Credential Manager so
normal use does not require manually replacing tokens.

## Planned connector stages

1. **Read-only connector transport:** all eight supported connectors, strict
   read-only tool allowlists, environment-token activation, and fake tests.
2. **Google OAuth:** one browser authorization flow for Gmail, Calendar, and
   Drive with refresh tokens protected by Windows.
3. **Microsoft OAuth:** one browser authorization flow for Outlook Mail,
   Outlook Calendar, Teams, and SharePoint.
4. **Approval-gated writes:** separate tools for sending mail and changing
   calendars. Every write will show the exact proposed action and require an
   explicit confirmation; no write tool is exposed yet.
5. **Daily context brief:** weather, calendar, important messages, Toronto
   alerts, and relevant memories combined into a concise optional briefing.
