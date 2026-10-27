# Wine Fridge — self-hosted wine fridge inventory

A Dockerized replacement for the old Google Apps Script wine-fridge app.
Photograph a wine label, a local LLM (via your llama.cpp server) identifies it,
you confirm/edit the details, and the bottle is stored in a local SQLite
database. No Google, no cloud — everything stays on your network.

## Features

- **Fridge view** — dark "Wine Fridge" board: each shelf is a row of bottle dots
  (color = red / white / rosé), with per-shelf counts. Tap a dot for details.
- **List mode** — grouped-by-shelf list with label thumbnails.
- **Search** — filters by wine, producer, variety, vintage, shelf, or notes.
- **Add flow** — camera capture → local LLM identification → editable form →
  shelf picker → save (the label photo is stored with the bottle).
- **Move / remove** bottles from the detail sheet.
- **Spreadsheet import** — one-time import of the old Google Sheet export,
  right from the app's Settings page (bundled file or upload your own .xlsx).
- **CSV export** for backups.

## Requirements

- Unraid (or any Docker host)
- A llama.cpp server with a **vision-capable (VL) model** loaded.
  A plain text model cannot read label photos. The app is configured for
  `Qwen-3.8-27B-Q4` at `192.168.1.132:8081` by default.

## Setup (Unraid via GitHub template)

The Unraid UI doesn't take compose files, so the image is published to
GitHub Container Registry (GHCR) by a GitHub Actions workflow, and Unraid
installs it from a template.

### 1. Create the GitHub repo

Create a repo named **`wine-fridge`** on your GitHub account
(the image name is derived from the repo name: `ghcr.io/<you>/wine-fridge`).
Then push this folder:

```bash
cd wine-fridge
git init
git add -A
git commit -m "Vinotag: self-hosted wine fridge inventory"
git remote add origin https://github.com/<you>/wine-fridge.git
git push -u origin main
```

> The template and workflow already reference `vtree64`. If the repo lives
> under a different account, search-and-replace `vtree64` in
> `unraid/wine-fridge.xml` and `.github/workflows/docker-publish.yml` first.

### 2. Let Actions build the image

Pushing to `main` triggers **Build and publish Docker image**
(Actions tab). It builds `linux/amd64` + `linux/arm64` and pushes
`ghcr.io/<you>/wine-fridge:latest` to GHCR. Takes a couple of minutes.
You can also run it manually via **Actions → workflow → Run workflow**.

### 3. Add the template in Unraid

In the Unraid UI: **Settings → Docker → Template URL** (or
**Docker → Add Container → paste a template URL**) and paste:

```
https://raw.githubusercontent.com/<you>/wine-fridge/main/unraid/wine-fridge.xml
```

Then **Docker → Add Container → Wine Fridge** and configure:

| Field | Value |
|-------|-------|
| Web UI Port | `8300` (any free port) |
| App Data | `/mnt/user/appdata/wine-fridge` (created automatically) |
| *Advanced* → `LLAMA_SERVER_URL` | `http://192.168.1.132:8081` |
| *Advanced* → `LLAMA_MODEL` | `Qwen-3.8-27B-Q4` |
| *Advanced* → `SHELVES` | `Shelf 1,Shelf 2,…,Shelf 7` |
| *Advanced* → `LLM_TIMEOUT_SECONDS` | `600` |

Start the container.

### 4. Import your inventory

Open `http://<unraid-ip>:8300` → **Settings → Import → Import bundled
spreadsheet**. Your 28 bottles from the old Google Sheet are baked into the
image and will be imported into the fresh database. Safe to re-run — bottles
that already exist are skipped. (You can also upload any .xlsx with the same
headers via **Import from file…**.)

### 5. Point the fridge QR code at the app

`http://<unraid-ip>:8300/?view=add` goes straight to the camera.

## Updating the app

Push a new commit to `main` → Actions rebuilds and pushes `:latest` →
in Unraid: **Docker → Wine Fridge → Stop**, then
**Actions → Re-deploy** (or delete + re-add from the template). Your data
lives in `/mnt/user/appdata/wine-fridge` and is untouched.

## Alternative: docker compose (any Docker host)

If you'd rather not use the GitHub flow:

```bash
docker compose up -d --build
```

then import via the app's Settings page (the bundled spreadsheet is in the
image) or `docker compose run --rm wine-fridge python import_xlsx.py`.

## Configuration (environment variables)

| Variable              | Default                     | Description                              |
|-----------------------|-----------------------------|------------------------------------------|
| `LLAMA_SERVER_URL`    | `http://192.168.1.132:8081` | llama.cpp server base URL                |
| `LLAMA_MODEL`         | `Qwen-3.8-27B-Q4`           | Model name (must be a vision model)      |
| `SHELVES`             | `Shelf 1` … `Shelf 7`       | Comma-separated shelf names              |
| `LLM_TIMEOUT_SECONDS` | `600`                       | Max wait for the model to answer         |
| `LLM_MAX_TOKENS`      | `1024`                      | Max response tokens                      |
| `LLM_TEMPERATURE`     | `0.1`                       | Sampling temperature                     |
| `DATA_DIR`            | `/app/data`                 | Where the SQLite DB lives (in container) |

## Data

- `/mnt/user/appdata/wine-fridge/inventory.db` — SQLite database
  (bottles + label photos). Back this folder up; it is the only state.
- `seed/Wine Inventory.xlsx` — the original spreadsheet, baked into the image
  for the one-time import.
- `GET /api/export.csv` — download the inventory as CSV.

## API

| Method | Path                        | Description                          |
|--------|-----------------------------|--------------------------------------|
| GET    | `/api/config`               | Shelves, LLM config, bottle count    |
| GET    | `/api/llm/status`           | llama.cpp reachability + model list  |
| POST   | `/api/analyze`              | `{image: dataUrl}` → wine fields     |
| GET    | `/api/bottles`              | List all bottles                     |
| POST   | `/api/bottles`              | Add a bottle (optional `label_image`)|
| PATCH  | `/api/bottles/{id}`         | Update fields (e.g. `shelf`)         |
| DELETE | `/api/bottles/{id}`         | Remove a bottle                      |
| GET    | `/api/bottles/{id}/image`   | Stored label photo                   |
| POST   | `/api/import`               | Import spreadsheet (multipart `file`, or bundled if omitted) |
| GET    | `/api/export.csv`           | CSV export                           |

## Troubleshooting

- **"llama.cpp error (400): … image … not supported"** — the loaded model is
  text-only. Load a vision model (e.g. a Qwen-VL variant) in llama.cpp.
- **Identification is very slow** — a 27B Q4 model is heavy. Options: a
  smaller VL model (3–8B), a GPU for llama.cpp, or lower the photo size
  (the app already downscales to 1600px).
- **Settings → Status says "Server up · model NOT loaded"** — the model name
  in `LLAMA_MODEL` doesn't match what llama.cpp reports. Check
  `curl http://192.168.1.132:8081/v1/models`.
- **Template doesn't appear in Unraid** — the Actions build must have
  finished first (check the Actions tab), and the repo must be public or
  Unraid must be able to pull from GHCR (public repos work without
  credentials).
- **Port already in use** — change the Web UI Port in the container's
  settings and restart.
