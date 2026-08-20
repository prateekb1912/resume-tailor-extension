# Tailr Chrome extension

This build connects to `https://tailr-api.onrender.com`. Each person creates or signs in to
their own Tailr account; API and database credentials are never included in the extension.

## Install from the ZIP

1. Unzip `tailr-extension.zip` to a permanent folder.
2. Open `chrome://extensions` in Google Chrome.
3. Enable **Developer mode**.
4. Click **Load unpacked** and select the unzipped folder containing `manifest.json`.
5. Pin Tailr, open it on a job page, and create an account or sign in.

Do not delete or move the unzipped folder while the extension is installed. Chrome loads the
extension directly from that folder. Reload it from `chrome://extensions` after replacing files
with a newer build.

## Local API development

Open **Connection settings** in the popup and use `http://localhost:8000`. Changing the API signs
the current session out because access tokens belong to the server that issued them.
