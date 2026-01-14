# Google Cloud Console OAuth Setup Guide

## Current Situation
- ✅ You have OAuth Client ID credentials (credentials.json)
- ✅ Your app can authenticate users via Google OAuth
- ⚠️ App is likely in "Testing" mode with limited users

## Add Test Users (5 minutes)

1. **Open Google Cloud Console:**
   https://console.cloud.google.com

2. **Navigate to OAuth Consent Screen:**
   - Select your project
   - Click "APIs & Services" (left menu)
   - Click "OAuth consent screen"

3. **Add Test Users:**
   - Scroll to "Test users" section
   - Click "+ ADD USERS"
   - Enter email addresses:
     * kartik@godamwale.com
     * systems@godamwale.com
   - Click "Save"

4. **Verify:**
   - Test users should now appear in the list
   - These users can now authenticate with your app

## Alternative: Publish App (For Production)

If you want ANY user to authenticate (not just test users):

1. **Review App Information:**
   - App name: "Gmail Integration for Saral ERP" (or similar)
   - User support email: Your email
   - Developer contact: Your email
   - App logo (optional)

2. **Click "PUBLISH APP":**
   - Review all information
   - Click "PUBLISH APP" button
   - Confirm

3. **App Status:**
   - Internal (Workspace): Only your organization → No verification needed
   - External: Anyone → May require Google verification for gmail.readonly scope

## What You DON'T Need

❌ Service Account - Not needed for user OAuth
❌ New credentials.json - Current one works for multiple users
❌ Multiple OAuth clients - One client handles all users

## How Multi-User OAuth Works

```
User Flow:
1. User clicks "Connect Gmail"
2. Redirects to Google login
3. User logs in with THEIR Gmail account
4. Google asks permission for your app
5. User approves
6. Token saved for THAT user's account
7. Next user repeats steps 1-6 with THEIR credentials
```

Each user authenticates with their own Gmail credentials. Your OAuth client (credentials.json) just facilitates the connection.

## Verification

After adding test users, try this:

```bash
# Start server
python manage.py runserver

# Open browser
http://localhost:8000/accounts/login/

# Login as admin (username: admin, password: [set earlier])
# Go to: http://localhost:8000/start-auth/
# Authenticate with kartik@godamwale.com or systems@godamwale.com
```

If the user is NOT in test users list, you'll see:
"Access blocked: This app's request is invalid"

If they ARE in test users, OAuth will work! ✅
