# Evaluation pipeline (public harness)

Public repo runs the candidate-submission evaluation. The scoring **prompts** and **assignment PDFs**
are NOT in this repo — they are private and pulled from S3 at runtime by the workflow. Candidate data
never reaches the public Actions log (pipeline output is suppressed; results go to the app via the
callback; only redacted errors are surfaced).

## One-time setup

### 1. Upload the private test bank to S3
From your app repo's `evaluation-pipeline/`:
```
aws s3 sync prompts      s3://nestack-neilp-hiring/eval-assets/prompts
aws s3 sync assignments  s3://nestack-neilp-hiring/eval-assets/assignments
```

### 2. Repo secrets (Settings -> Secrets and variables -> Actions -> Secrets)
| Secret | Value |
|---|---|
| `OPENAI_API_KEY` | your OpenAI key |
| `EVAL_GITHUB_TOKEN` | PAT that can accept invitations / read candidate repos |
| `EVAL_CALLBACK_URL` | `https://neilp.nestack.ai/api/eval/callback` |
| `EVAL_CALLBACK_SECRET` | same value as the app's `EVAL_CALLBACK_SECRET` |
| `AWS_ACCESS_KEY_ID` | key with `s3:GetObject` on `eval-assets/*` |
| `AWS_SECRET_ACCESS_KEY` | matching secret |
| `EVAL_ASSETS_BUCKET` | `nestack-neilp-hiring` |

### 3. Repo variables (…-> Variables)
| Variable | Value |
|---|---|
| `OPENAI_MODEL` | e.g. `gpt-4o-mini` |
| `AWS_REGION` | `ap-south-1` |

### 4. Point the app at this repo
In the app (Vercel env):
- `GH_REPO=ArunK-Nestack/xb82o898yb24x2zn09`
- `GH_DISPATCH_TOKEN` = a PAT with `actions: write` on this repo (so the app can dispatch `evaluate.yml`).

## Test
```
gh workflow run evaluate.yml -f jobId=<id> -f repoUrl=https://github.com/octocat/Hello-World
```
Check the app DB / `/api/eval/callback` receives the result. The public Actions log should show only
"::error::…" lines on failure, never candidate data.
