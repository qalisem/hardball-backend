# Deployment Guide

End-to-end walkthrough for deploying Hardball to AWS as it currently runs in production. Region: `us-east-1`. Live URLs:

- Frontend: https://dz3csw06yjedg.cloudfront.net
- Backend (origin): http://hardball-api-prod.eba-2mvwmpmr.us-east-1.elasticbeanstalk.com
- CloudFront distribution: `E1AEOT2IV7WSET`
- S3 bucket: `hardball-web-qali`

## Prerequisites

- AWS account with billing enabled
- AWS CLI: `brew install awscli` or `pip install awscli`
- Elastic Beanstalk CLI: `pip install awsebcli`
- Run `aws configure` once (access key, secret, default region `us-east-1`, output `json`)

---

## Part 1 — Backend on Elastic Beanstalk

### 1. Initialize the EB application

From inside `hardball-backend/`:

```bash
eb init -p python-3.11 hardball-api --region us-east-1
```

This creates `.elasticbeanstalk/` (gitignored) and registers the application with AWS.

### 2. Create the environment

```bash
eb create hardball-api-prod \
  --instance_type t3.micro \
  --single
```

`--single` skips the load balancer (saves ~$18/mo) and gives you a public IPv4 directly on the EC2 instance. First create takes ~5 minutes — EB provisions EC2, installs Python 3.11, runs `pip install -r requirements.txt`, and starts Gunicorn via the `Procfile`.

### 3. Configure environment variables

```bash
eb setenv \
  ANTHROPIC_API_KEY=sk-ant-your-real-key-here \
  ANTHROPIC_MODEL=claude-haiku-4-5-20251001 \
  ALLOWED_ORIGINS=https://dz3csw06yjedg.cloudfront.net
```

Setting all variables in one `eb setenv` call is important — each invocation does a full replace of the unmanaged env, not a merge.

For a more disciplined setup, store the key in Secrets Manager and grant `secretsmanager:GetSecretValue` to the EB instance role; the application code reads `os.environ` either way.

### 4. Deploy

```bash
eb deploy
```

EB zips files tracked by git, uploads to S3, and rolls them out. Total time: ~90 seconds. **`eb deploy` only ships files committed to git**; uncommitted edits are silently skipped (use `eb deploy --staged` to ship the staging area, or just commit first).

### 5. Verify

```bash
eb open
curl http://hardball-api-prod.eba-2mvwmpmr.us-east-1.elasticbeanstalk.com/api/health
# {"status":"ok","service":"hardball-api",...,"team_count":30}
```

### 6. Logs

```bash
eb logs --stream
```

---

## Part 2 — Frontend on S3

### 1. Build the React app

```bash
cd hardball-web
npm install
npm run build         # outputs to dist/
```

`VITE_API_BASE` should be empty in the production build so the frontend issues same-origin requests to `/api/*` (proxied by CloudFront in Part 3).

### 2. Create the S3 bucket

```bash
aws s3 mb s3://hardball-web-qali --region us-east-1
aws s3 website s3://hardball-web-qali --index-document index.html
```

### 3. Bucket policy (public read for static hosting)

`bucket-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "PublicReadGetObject",
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::hardball-web-qali/*"
  }]
}
```

```bash
aws s3api put-public-access-block --bucket hardball-web-qali \
  --public-access-block-configuration "BlockPublicPolicy=false,RestrictPublicBuckets=false,BlockPublicAcls=false,IgnorePublicAcls=false"
aws s3api put-bucket-policy --bucket hardball-web-qali --policy file://bucket-policy.json
```

### 4. Upload the build

```bash
aws s3 sync dist/ s3://hardball-web-qali --delete
```

---

## Part 3 — CloudFront

### 1. Create the distribution

In the AWS Console (CloudFront → Create distribution):

- **Origin domain:** `hardball-web-qali.s3-website-us-east-1.amazonaws.com`  *(the website endpoint — **not** the regular `s3.amazonaws.com` endpoint, which doesn't honor the index-document setting)*
- **Origin protocol:** HTTP only (S3 website endpoints don't support HTTPS)
- **Viewer protocol policy:** Redirect HTTP to HTTPS
- **Default root object:** `index.html`
- **Cache policy:** CachingOptimized
- **Price class:** Use only North America and Europe

Wait ~10 minutes for the distribution to deploy. Note the distribution ID (`E1AEOT2IV7WSET`) and domain (`dz3csw06yjedg.cloudfront.net`).

### 2. Add the `/api/*` behavior (the magic step)

This is what makes the API same-origin from the browser's perspective.

- **Create origin** → `hardball-api-prod.eba-2mvwmpmr.us-east-1.elasticbeanstalk.com`, HTTP only, port 80
- **Create behavior:**
  - Path pattern: `/api/*`
  - Origin: the EB origin you just created
  - Viewer protocol policy: Redirect HTTP to HTTPS
  - Allowed methods: `GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE`
  - Cache policy: CachingDisabled
  - Origin request policy: AllViewer

Without this, the HTTPS frontend cannot call the HTTP-only EB endpoint — the browser blocks it as mixed content.

### 3. Invalidate the cache after a frontend update

```bash
aws s3 sync dist/ s3://hardball-web-qali --delete
aws cloudfront create-invalidation \
  --distribution-id E1AEOT2IV7WSET \
  --paths "/*"
```

---

## Cost expectations

| Service                | Cost                                                       |
|------------------------|------------------------------------------------------------|
| EB `t3.micro` single   | free tier 12mo, ~$8/mo after                               |
| S3 (storage + GET)     | <$0.50/mo for portfolio traffic                            |
| CloudFront             | first 1 TB egress / 10M requests free, ~$0/mo              |
| Secrets Manager (opt)  | $0.40/mo per secret                                        |
| Anthropic API          | pay-per-token, ~$1–3/mo for demo traffic on Haiku 4.5      |

**Realistic total: ~$10/mo after free tier.** Tear down with `eb terminate hardball-api-prod` when not actively demoing.

---

## Troubleshooting

**502 Bad Gateway from `/api/*`.** Gunicorn crashed on boot. `eb logs --stream` and look for the import error or missing env var. The most common case in this project's history: an Anthropic 404 because the model env var pointed at a retired model — fix with `eb setenv ANTHROPIC_MODEL=claude-haiku-4-5-20251001`.

**Mixed Content errors in the browser console** ("Blocked loading mixed active content http://..."). The frontend is hardcoded to an HTTP URL. Set `VITE_API_BASE=` (empty) so requests go to relative `/api/*`, rebuild, re-sync to S3, invalidate.

**CORS error: "blocked by CORS policy".** `ALLOWED_ORIGINS` on the backend doesn't match the CloudFront domain exactly. Compare for trailing slashes, `http` vs `https`, and the `www.` prefix. Re-set everything in one `eb setenv` call (each call replaces the full unmanaged env).

**`eb deploy` reports success but the code didn't change.** EB ships files committed to git, not the working tree. `git status`, commit, redeploy. Or run `eb deploy --staged` to ship the index.

**Anthropic 404 / "model not found".** The model id is stale. Sanity check the active model list:

```bash
curl https://api.anthropic.com/v1/models \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01"
```

Then `eb setenv ANTHROPIC_MODEL=<a model id from that list>`.

**`/api/*` returns 403 from CloudFront.** The `/api/*` behavior is missing or its origin is misconfigured. Re-check Part 3 step 2 — pay attention to the cache policy (must be CachingDisabled) and the allowed methods list (must include POST).

**Frontend loads but team list is empty.** The `/api/teams` request is reaching the wrong host. Confirm the network tab shows `dz3csw06yjedg.cloudfront.net/api/teams`, not `localhost:5000`. Common cause: `VITE_API_BASE` was set to a non-empty string at build time, so the frontend ignored the same-origin path.
