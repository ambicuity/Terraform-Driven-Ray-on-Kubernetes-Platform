# GitHub App Authentication Flow

This document explains how the GitHub App authenticates and generates short-lived tokens for infrastructure operations.

## Overview

Our infrastructure platform uses **GitHub App Installation Tokens** instead of Personal Access Tokens (PATs) for all operations. This provides enterprise-grade security with automatic token rotation and minimal permissions.

## Authentication Flow

### Step 1: JWT Generation

The GitHub App authenticates itself using a JSON Web Token (JWT):

```yaml
# In GitHub Actions workflow
- name: Generate JWT
  id: generate-jwt
  run: |
    # JWT claims
    iat=$(date +%s)
    exp=$((iat + 600))  # 10 minute expiration
    
    # Create JWT payload
    payload=$(cat <<EOF
    {
      "iat": $iat,
      "exp": $exp,
      "iss": "${{ secrets.APP_ID }}"
    }
    EOF
    )
    
    # Sign with private key
    jwt=$(echo -n "$payload" | openssl dgst -sha256 -sign <(echo "${{ secrets.APP_PRIVATE_KEY }}") | base64)
    echo "::add-mask::$jwt"
    echo "jwt=$jwt" >> $GITHUB_OUTPUT
```

### Step 2: Installation Token Request

Use the JWT to request an installation token:

```yaml
- name: Get Installation Token
  id: get-token
  run: |
    response=$(curl -s -X POST \
      -H "Authorization: Bearer ${{ steps.generate-jwt.outputs.jwt }}" \
      -H "Accept: application/vnd.github+json" \
      "https://api.github.com/app/installations/${{ secrets.INSTALLATION_ID }}/access_tokens")
    
    token=$(echo "$response" | jq -r .token)
    expires=$(echo "$response" | jq -r .expires_at)
    
    echo "::add-mask::$token"
    echo "token=$token" >> $GITHUB_OUTPUT
    echo "Token expires at: $expires"
```

### Step 3: Use Token in Operations

The installation token can now be used for:

```yaml
# Git operations
- name: Checkout with App Token
  uses: actions/checkout@v4
  with:
    token: ${{ steps.get-token.outputs.token }}

# API calls
- name: Post PR Comment
  run: |
    curl -X POST \
      -H "Authorization: token ${{ steps.get-token.outputs.token }}" \
      -H "Accept: application/vnd.github+json" \
      "${{ github.api_url }}/repos/${{ github.repository }}/issues/${{ github.event.pull_request.number }}/comments" \
      -d '{"body": "Terraform plan completed ✅"}'

# Cloud provider authentication (via OIDC)
- name: Configure AWS Credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
    aws-region: us-east-1
    # GitHub token used for OIDC identity
    github-token: ${{ steps.get-token.outputs.token }}
```

## Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         GitHub App                              │
│                                                                 │
│  Credentials:                                                   │
│  - APP_ID (e.g., 123456)                                       │
│  - APP_PRIVATE_KEY (RSA PEM format)                            │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │ 1. Generate JWT
                     │    (signed with private key)
                     │    expires in 10 minutes
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│                      GitHub API                                 │
│                                                                 │
│  POST /app/installations/{INSTALLATION_ID}/access_tokens        │
│  Authorization: Bearer {JWT}                                    │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │ 2. Returns Installation Token
                     │    {
                     │      "token": "ghs_xxxx",
                     │      "expires_at": "2024-01-01T13:00:00Z",
                     │      "permissions": {...}
                     │    }
                     │    expires in 1 hour
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│                   GitHub Actions Workflow                       │
│                                                                 │
│  Jobs:                                                          │
│  - Terraform Plan                                               │
│  - Terraform Apply                                              │
│  - Ray Deployment                                               │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │ 3. Use token for operations
                     │
        ┌────────────┼────────────┬─────────────┐
        │            │            │             │
        ↓            ↓            ↓             ↓
   ┌─────────┐  ┌────────┐  ┌──────────┐  ┌─────────┐
   │   Git   │  │  API   │  │  Cloud   │  │  K8s    │
   │   Ops   │  │  Calls │  │  Auth    │  │  Access │
   └─────────┘  └────────┘  └──────────┘  └─────────┘
```

## Token Lifecycle

1. **Generation**: Workflow starts → JWT created → Installation token requested
2. **Active**: Token valid for 1 hour (GitHub's limit)
3. **Expiration**: Token automatically expires, no manual cleanup needed
4. **Renewal**: Next workflow run generates a new token

## Security Properties

### ✅ What We Achieve

1. **Short-lived credentials**: Tokens expire in 1 hour
2. **No secret sprawl**: Only 3 secrets needed (APP_ID, PRIVATE_KEY, INSTALLATION_ID)
3. **Automatic rotation**: Every workflow run gets a new token
4. **Least privilege**: App has only required permissions
5. **Audit trail**: All actions logged to app installation
6. **Revocable**: Uninstall app to revoke all access immediately

### ❌ What We Avoid

1. **Long-lived PATs**: Never expire unless manually revoked
2. **User-scoped access**: PATs have user's full permissions
3. **Credential rotation**: PATs require manual rotation
4. **Shared secrets**: Multiple PATs for different services
5. **Attribution issues**: PAT actions attributed to user, not automation

## Cloud Provider Integration

### AWS (OIDC)

```yaml
- name: Configure AWS Credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::123456789012:role/GitHubAppTerraformRole
    aws-region: us-east-1
    # OIDC identity uses GitHub token
    github-token: ${{ steps.get-token.outputs.token }}
```

### GCP (Workload Identity)

```yaml
- name: Authenticate to Google Cloud
  uses: google-github-actions/auth@v2
  with:
    workload_identity_provider: 'projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider'
    service_account: 'terraform@project-id.iam.gserviceaccount.com'
    token_format: 'access_token'
    github_token: ${{ steps.get-token.outputs.token }}
```

## Troubleshooting

### JWT Expired Error
**Symptom**: `401 Unauthorized - JWT has expired`
**Solution**: JWT is valid for 10 minutes. Regenerate before each API call.

### Invalid Installation ID
**Symptom**: `404 Not Found`
**Solution**: Verify `INSTALLATION_ID` matches your org's installation. Find it at:
`https://github.com/settings/installations/{INSTALLATION_ID}`

### Token Permission Denied
**Symptom**: `403 Forbidden - Resource not accessible by integration`
**Solution**: Check app permissions match requirements in `permissions.md`

### Private Key Format Error
**Symptom**: `Invalid key format`
**Solution**: Ensure private key includes:
```
-----BEGIN RSA PRIVATE KEY-----
...
-----END RSA PRIVATE KEY-----
```

## References

- [GitHub Apps Authentication](https://docs.github.com/en/developers/apps/building-github-apps/authenticating-with-github-apps)
- [Installation Access Tokens](https://docs.github.com/en/rest/apps/apps#create-an-installation-access-token-for-an-app)
- [JWT Claims](https://jwt.io/)
- [OpenID Connect in Cloud Providers](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
