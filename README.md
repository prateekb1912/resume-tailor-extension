# Tailr

Monorepo for the Tailr product — tailor your resume to any job description.

## Layout

- `extension/` — Chrome extension (MV3). Reads the job description on a page, shows a
  match score, and tailors the user's resume to it.
- `server/` — FastAPI backend (auth, resume parsing, JD-tailored resume generation).
  See [server/README](server/README.md) for setup. *(added during Phase 0/1)*
- `workflows/` — n8n workflow exports (local only, gitignored). Being ported into
  `server/` incrementally; Companies Seeding + Job Fetch still run in n8n for now.

## Status

Productionizing from a single-user local setup (extension → local n8n) into a
multi-user hosted service. See the plan for phasing.

## Share the extension

Build the unpacked-extension ZIP with:

```bash
./scripts/package-extension.sh
```

The output is `dist/tailr-extension.zip`. Recipients unzip it and load the resulting folder from
`chrome://extensions` using **Developer mode → Load unpacked**. Each recipient signs in with their
own Tailr account; server secrets and database credentials stay on the deployed API.
