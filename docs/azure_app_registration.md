# Set up Azure App Registration for Data Fetching

In order to run the MS Graph API related code without user interaction, we need to set up Microsoft Authentication Library Device Flow.

To do this, there are multiple steps.

## 1. Create App Registration

1. Go to [https://portal.azure.com]
2. Navigate to: **Azure Active Directory → App registrations**
3. Click **New registration**
4. Configure:
    - **Name**:
    - **Supported account types**: *Accounts in any organizational directory and personal Microsoft accounts*
5. Click **Register**

## 2. Enable Public Client Flow

1. Go to **Authentication**
2. Under **Advanced settings**:
   - Enable **Allow public client flows**
3. Save

## 3. Save Application ID

- After the App registration is complete, store the Application/Client ID in the `.env` file as the `CLIENT_ID`

## 4. Add API Permissions

1. Go to **API permissions**
2. Click **Add a permission**
3. Select **Microsoft Graph**
4. Select **Delegated permissions**
5. Add:
   - `Files.Read.All`
6. Click **Add permissions**
