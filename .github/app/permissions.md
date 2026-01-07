# GitHub App Permissions

This document specifies the required permissions for the GitHub App that manages infrastructure operations.

## Repository Permissions

| Permission | Access Level | Purpose |
|------------|-------------|---------|
| Actions | Read | Read workflow run status and logs |
| Contents | Read | Read repository code and Terraform configurations |
| Pull Requests | Write | Post plan output as PR comments |
| Issues | Write | Create issues for cost reports and alerts |
| Checks | Write | Report Terraform validation and policy check results |

## Organization Permissions

| Permission | Access Level | Purpose |
|------------|-------------|---------|
| Members | Read | (Optional) Validate team-based approvals |

## Webhook Events

The GitHub App should subscribe to:

- `pull_request` - Trigger terraform plan on PR creation/update
- `push` - Trigger terraform apply on merge to main
- `workflow_dispatch` - Allow manual workflow triggers
- `schedule` - Enable daily cost reports

## Why These Permissions?

### Minimal Scope
We request only what's needed for infrastructure automation:
- **No admin access** to repository settings
- **No secrets access** (we use app authentication)
- **No deployment keys** (replaced by app tokens)

### Security Benefits
1. **Short-lived tokens**: Installation tokens expire in 1 hour
2. **Auditable**: All actions tracked to app installation
3. **Revocable**: Uninstall app to immediately revoke all access
4. **Scoped**: Permissions limited to specific actions

### vs Personal Access Tokens (PATs)

| Feature | GitHub App | PAT |
|---------|-----------|-----|
| Token lifetime | 1 hour | Until revoked |
| Permissions | Granular | User's full access |
| Audit trail | App-specific | User actions |
| Rotation | Automatic | Manual |
| Team management | Org-level | User-level |
| Security | ✅ Enterprise-grade | ❌ Broad scope |

## Installation Requirements

When installing this app, you'll need:

1. **APP_ID** - The numeric ID of your GitHub App
2. **APP_PRIVATE_KEY** - The RSA private key (PEM format)
3. **INSTALLATION_ID** - The installation ID for your organization

These values are added as **GitHub Secrets** (not environment variables) and are the only secrets required.

## Token Generation Flow

```
GitHub App (APP_ID + PRIVATE_KEY)
  ↓ Generate JWT
GitHub API (/app/installations/{INSTALLATION_ID}/access_tokens)
  ↓ Returns installation token (expires in 1 hour)
GitHub Actions workflow
  ↓ Use token for git operations and API calls
Terraform/Helm/kubectl operations
```

## Security Best Practices

1. **Never commit** APP_PRIVATE_KEY to version control
2. **Rotate** private keys every 90 days
3. **Monitor** app installation events
4. **Limit** app installation to required repositories only
5. **Review** audit logs monthly

## Compliance

This permission model supports:
- SOC 2 Type II requirements
- Least privilege access (CIS benchmark)
- Zero trust architecture
- NIST Cybersecurity Framework
