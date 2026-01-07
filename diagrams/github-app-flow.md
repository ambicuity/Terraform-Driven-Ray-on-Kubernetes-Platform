# GitHub App Authentication Flow

This diagram illustrates the authentication flow from GitHub App to infrastructure operations.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          GitHub App                                 │
│                                                                     │
│  Configuration:                                                     │
│  • APP_ID: 123456                                                  │
│  • PRIVATE_KEY: RSA-2048 PEM                                       │
│  • INSTALLATION_ID: 789012                                         │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     │ Step 1: Generate JWT Token
                     │ (expires in 10 minutes)
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      GitHub API                                     │
│                                                                     │
│  POST /app/installations/{INSTALLATION_ID}/access_tokens            │
│  Authorization: Bearer {JWT}                                        │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     │ Step 2: Receive Installation Token
                     │ {
                     │   "token": "ghs_...",
                     │   "expires_at": "2024-12-01T14:00:00Z",
                     │   "permissions": {...}
                     │ }
                     │ (expires in 1 hour)
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│                   GitHub Actions Workflow                           │
│                                                                     │
│  Environment Variables:                                             │
│  • GITHUB_TOKEN: {installation_token}                              │
│  • AWS_REGION: us-east-1                                           │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     │ Step 3: Use Token for Operations
                     │
      ┌──────────────┼──────────────┬──────────────┬──────────────┐
      │              │              │              │              │
      ↓              ↓              ↓              ↓              ↓
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│   Git    │  │ GitHub   │  │   AWS    │  │   K8s    │  │   Ray    │
│   Ops    │  │   API    │  │   OIDC   │  │  Access  │  │  Deploy  │
└──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
   Clone         PR           Assume       kubectl      helm install
   Commit      Comments        Role        commands        Ray
   Push         Issues       Terraform
```

**Security Benefits:**
- ✅ Tokens auto-expire (1 hour max)
- ✅ No long-lived credentials
- ✅ Audit trail per app
- ✅ Granular permissions
- ✅ Revocable via app uninstall

## Placeholder for Visual Diagram

A detailed visual diagram showing the GitHub App authentication flow will be added here.
This can be created using tools like draw.io, Lucidchart, or Mermaid.

**Recommended tools:**
- Mermaid (in-repo diagrams)
- draw.io (professional diagrams)
- PlantUML (developer-friendly)
