# Calendar MCP Server - Streamable HTTP Implementation

This project provides a complete, deployable solution for running a Google Calendar MCP server using the streamable HTTP protocol. It is designed for easy deployment on Render.com and includes a secure backend for managing Google OAuth credentials.

## Features

- **FastMCP 2.0**: Built with the latest version of FastMCP for efficient, streamable communication.
- **PostgreSQL Backend**: Securely stores Google OAuth 2.0 credentials in a PostgreSQL database.
- **Render.com Ready**: Includes a `render.yaml` file for one-click deployment of the MCP server, admin panel, and database.
- **Web Admin Interface**: A Flask-based web app allows you to easily and securely authorize Google accounts and manage credentials without exposing tokens.
- **API Key Authentication**: Protects your MCP server endpoints from unauthorized access.

## Deployment to Render

Follow these steps to get your Calendar MCP server live.

### 1. Fork and Connect to Render
1.  **Fork this repository** to your own GitHub account.
2.  Go to the [Render Dashboard](https://dashboard.render.com/) and create a new **Blueprint Instance**.
3.  Connect the GitHub repository you just forked. Render will automatically detect and apply the `render.yaml` configuration.

This will create three services:
- A PostgreSQL database (`calendar-mcp-db`).
- The MCP server web service (`calendar-mcp-server`).
- The admin panel web service (`calendar-mcp-admin`).

### 2. Configure Google OAuth Credentials
1.  Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  Create a new project or select an existing one.
3.  **Enable the Google Calendar API** for your project.
4.  Go to "APIs & Services" -> "Credentials".
5.  Click "+ CREATE CREDENTIALS" -> "OAuth client ID".
6.  Select **Application type: Web application**.
7.  Under "Authorized redirect URIs", click "+ ADD URI" and enter the URL for your admin panel's callback. You can find this URL on the Render dashboard for the `calendar-mcp-admin` service. It will look like: `https://calendar-mcp-admin.onrender.com/oauth2callback`.
8.  Click "CREATE". Copy the **Client ID** and **Client Secret**.

### 3. Set Environment Variables in Render
1.  In your Render dashboard, navigate to the `calendar-mcp-admin` service.
2.  Go to the **"Environment"** tab.
3.  Add the following environment variables as **Secret Files** or regular environment variables:
    - `GOOGLE_CLIENT_ID`: The Client ID you copied from Google.
    - `GOOGLE_CLIENT_SECRET`: The Client Secret you copied from Google.
    - `REDIRECT_URI`: The full callback URL you added in the previous step (`https://calendar-mcp-admin.onrender.com/oauth2callback`).

### 4. Authorize Your Google Account
1.  Wait for the `calendar-mcp-admin` service to deploy.
2.  Open the URL for your admin service.
3.  Log in using the admin credentials. The username is `admin` and the password can be found in the `ADMIN_PASSWORD` environment variable of the `calendar-mcp-admin` service on Render.
4.  In the admin dashboard, enter a User ID (e.g., `default`) and click "Setup with Google OAuth".
5.  You will be redirected to Google to authorize the application. Complete the flow.
6.  Once finished, your credentials will be securely stored in the database, and the MCP server can now access your calendar.

## Connecting to Your MCP Server

Your MCP server is now ready to be used by any MCP-compatible client, such as n8n agents, Claude, or the VS Code MCP extension.

- **Server URL**: `https://calendar-mcp-server.onrender.com/mcp/` (replace with your actual server URL from Render).
- **Authentication**: Use Header Authentication.
  - **Header Name**: `X-API-Key`
  - **Header Value**: The value of the `CALENDAR_MCP_SERVER_API_KEY` environment variable from the `calendar-mcp-server` service on Render.
