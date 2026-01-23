# Credential Rotation Guide

## When to Rotate Credentials

Rotate your credentials immediately if:
- They were accidentally committed to git
- A team member with access leaves
- You suspect unauthorized access
- As part of regular security hygiene (every 90 days)

---

## WhatsApp Cloud API Credentials

### 1. Regenerate App Secret

1. Go to [Meta for Developers](https://developers.facebook.com/)
2. Select your WhatsApp app
3. **Settings → Basic → App Secret**
4. Click "Show" → "Change"
5. Copy the new secret
6. Update `.env`:
   ```
   WHATSAPP_APP_SECRET=<new_secret>
   ```

### 2. Generate New Access Token

1. In Meta Business Settings → System Users
2. Select your system user
3. Click "Generate new token"
4. Select permissions: `whatsapp_business_messaging`, `whatsapp_business_management`
5. Update `.env`:
   ```
   WHATSAPP_TOKEN=<new_token>
   ```

---

## Google API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services → Credentials**
3. Find your API key → Click the 3-dot menu → "Regenerate key"
4. Update `.env`:
   ```
   GOOGLE_API_KEY=<new_key>
   ```

**Tip:** Restrict your API key to specific APIs and HTTP referrers for additional security.

---

## Super Admin Password

1. Generate a strong password (16+ characters, mixed case, numbers, symbols)
2. Update `.env`:
   ```
   SUPER_ADMIN_PASSWORD=<strong_password>
   ```
3. Update the database:
   ```bash
   python scripts/create_super_admin.py
   ```

---

## SECRET_KEY (Session Signing)

Generate a new 256-bit secret:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Update `.env`:
```
SECRET_KEY=<output_from_above>
```

> ⚠️ **Warning:** Rotating SECRET_KEY will invalidate all active user sessions.

---

## Verification Checklist

After rotating credentials:

- [ ] Old credentials revoked at source (Meta, Google, etc.)
- [ ] New credentials added to `.env` (NOT committed to git)
- [ ] Application tested locally
- [ ] Production environment variables updated
- [ ] Active sessions re-authenticated if needed
