# Running the container in the cloud

These steps are the same on every cloud. Only the product names and the exact commands differ, and
you can find those in your provider's documentation for the service named in each step. The image
needs no cloud-specific code and no secrets.

## What the container does

Started with no command, it runs `web-scraper-run`: download one page, save the embedded JSON, and exit.

| Setting | How | Meaning |
|---------|-----|---------|
| `SCRAPER_URL` | environment variable, **required** | page to download (`http://` or `https://`) |
| `SCRAPER_STATE_PATH` | environment variable, optional | dotted path to the listings array; also writes `items_<timestamp>.jsonl` |
| `/data` | folder inside the container | all output is written here (mount a volume to keep it) |

Output in `/data`, with the UTC start time of the run in each name (for example
`20261106T170703Z`), so runs never overwrite each other: `page1_<timestamp>.html` (raw page),
`raw_<timestamp>.json` (whole embedded state), and, if `SCRAPER_STATE_PATH` is set,
`items_<timestamp>.jsonl` (one listing per line). Exit code `0` means success; any other code means
a step failed and the job should be marked failed.

## 1. Test locally first

```bash
docker build -t web-scraper .
mkdir -p data
docker run --rm --user $(id -u):$(id -g) -v "$PWD/data:/data" \
  -e SCRAPER_URL=https://example.com/listings \
  -e SCRAPER_STATE_PATH=data.results.items \
  web-scraper
```

If this works, the same image and the same two variables work in the cloud.

## 2. Build for the cloud's CPU type

Most clouds run `linux/amd64`. If you build on an ARM machine (for example Apple Silicon), say so
explicitly:

```bash
docker build --platform linux/amd64 -t web-scraper .
```

## 3. Push the image to a registry the cloud can pull from

```bash
docker tag web-scraper <registry>/<path>/web-scraper:<version>
docker login <registry>                      # or the provider's login helper
docker push <registry>/<path>/web-scraper:<version>
```

Use a version tag (`0.1.0`, a git commit) instead of `latest`, so a job always runs a known image.

| Cloud | Registry |
|-------|----------|
| AWS | Elastic Container Registry (ECR) |
| Google Cloud | Artifact Registry |
| Azure | Azure Container Registry (ACR) |
| Any / Kubernetes | Docker Hub, GitHub Container Registry, or your own |

## 4. Create a job, not a service

This container starts, finishes, and exits. Use the cloud's **run-to-completion** product. A normal
"service" or "web app" expects a listening port and restarts the container when it exits.

| Cloud | Product |
|-------|---------|
| AWS | ECS task on Fargate (or AWS Batch) |
| Google Cloud | Cloud Run job |
| Azure | Container Apps job |
| Kubernetes | `Job` (or `CronJob`) |

Settings to fill in, the same everywhere:

| Setting | Value |
|---------|-------|
| Image | the pushed `<registry>/<path>/web-scraper:<version>` |
| Command / args | leave empty (the image default runs `web-scraper-run`) |
| Environment variables | `SCRAPER_URL`, and `SCRAPER_STATE_PATH` if you want the `items_<timestamp>.jsonl` file |
| Ports / health check | none |
| Restart policy | never, or on failure with at most 1-2 retries |
| Task timeout | a few minutes (the page download itself times out after 30 s) |
| CPU / memory | small, for example 0.5 vCPU and 512 MB; raise it if the job is killed for memory |

## 5. Keep the results: attach storage at `/data`

A job's own disk is deleted when the job ends. Mount a volume at `/data` so the files outlive the job.

| Cloud | Storage to mount at `/data` |
|-------|-----------------------------|
| AWS | EFS file system |
| Google Cloud | Cloud Storage bucket (volume mount) or Filestore |
| Azure | Azure Files share |
| Kubernetes | `PersistentVolumeClaim` |

The container runs as root by default, so it can write to such a mount without extra permission
setup. If your platform forces a non-root user, make the mounted storage writable for that user.

## 6. Give the job an identity, not keys

If the job needs to read secrets or reach private storage, attach the cloud's built-in identity to
the job (an IAM role, service account, or managed identity) and grant it only what it needs.
Do not put credentials in the image or in `SCRAPER_URL`. If the URL itself contains a token, store
it in the provider's secret manager and inject it into the job as the `SCRAPER_URL` variable.

## 7. Network access

The job must be able to reach the target site. Jobs in a private network (VPC / VNet) need an
outbound route to the internet, such as a NAT gateway. Check the site's `robots.txt` and terms of
service before scheduling automated downloads.

## 8. Run it and check the result

1. Start the job by hand once.
2. Read the logs: they should contain `saved ... characters to page1_<timestamp>.html` and `extracted ... to raw_<timestamp>.json`.
3. Confirm the job ended with exit code `0`.
4. Look in the storage behind `/data` for `raw_<timestamp>.json` (and `items_<timestamp>.jsonl`).

| Exit code | Meaning |
|-----------|---------|
| `0` | success |
| `1` | download or extract failed (see the `error:` line in the logs) |
| `2` | `SCRAPER_URL` is not set, or a command line was invalid |

## 9. Schedule it

Use the cloud's scheduler to start the job: EventBridge Scheduler (AWS), Cloud Scheduler (Google
Cloud), a schedule trigger on the Container Apps job (Azure), or a `CronJob` (Kubernetes). Every
run writes new files with its own timestamp, so the history builds up in the storage behind `/data`
(clean it up yourself if it grows too large).

## What to customize per cloud

Only these values change from one cloud to the next:

1. the registry address in the image name,
2. the job product and the commands for your provider,
3. the storage you mount at `/data`,
4. the scheduler,
5. `SCRAPER_URL` and `SCRAPER_STATE_PATH`.
