"""
Stage 2 script (not wired into the workflow yet).

What this needs to do, end to end:
  1. Auth to Microsoft Graph with the service principal (msal).
  2. Download the current signals + SBTi target lists from SharePoint.
  3. Append/merge whatever new rows your pipeline produced this run.
  4. Upload the merged lists back to SharePoint (so it stays the source of truth).
  5. Write the same merged lists out as flat JSON files into ../ (the deploy
     folder), overwriting signals.json and sbti_targets.json, so the next
     step in the workflow can deploy them next to index.html.

Fill in the Graph calls for your specific SharePoint site/list. Skeleton below.
"""

import json
import os
from pathlib import Path

import msal
import requests

TENANT_ID = os.environ["AZURE_TENANT_ID"]
CLIENT_ID = os.environ["AZURE_CLIENT_ID"]
CLIENT_SECRET = os.environ["AZURE_CLIENT_SECRET"]
SITE_ID = os.environ["SHAREPOINT_SITE_ID"]

DEPLOY_DIR = Path(__file__).resolve().parent.parent  # the folder deployed to Azure SWA
SIGNALS_OUT = DEPLOY_DIR / "signals.json"
SBTI_OUT = DEPLOY_DIR / "sbti_targets.json"


def get_graph_token() -> str:
    app = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        raise RuntimeError(f"Auth failed: {result.get('error_description')}")
    return result["access_token"]


def download_json_file(token: str, drive_item_path: str) -> list:
    """Download an existing JSON file from a SharePoint document library."""
    url = f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}/drive/root:/{drive_item_path}:/content"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    return resp.json()


def upload_json_file(token: str, drive_item_path: str, data: list) -> None:
    """Overwrite a JSON file in SharePoint with the merged dataset."""
    url = f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}/drive/root:/{drive_item_path}:/content"
    resp = requests.put(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
    )
    resp.raise_for_status()


def append_new_signals(existing: list, new_rows: list) -> list:
    """
    Merge new pipeline output into the existing list.
    Adjust the de-dupe key to whatever uniquely identifies a signal
    (e.g. source_url + headline) so re-runs don't create duplicates.
    """
    seen = {(row.get("source_url"), row.get("headline")) for row in existing}
    merged = list(existing)
    for row in new_rows:
        key = (row.get("source_url"), row.get("headline"))
        if key not in seen:
            merged.append(row)
            seen.add(key)
    return merged


def main() -> None:
    token = get_graph_token()

    # --- SIGNALS ---
    current_signals = download_json_file(token, "YourLibrary/signals.json")
    new_signals = []  # TODO: plug in your pipeline's freshly generated rows here
    merged_signals = append_new_signals(current_signals, new_signals)
    upload_json_file(token, "YourLibrary/signals.json", merged_signals)
    SIGNALS_OUT.write_text(
        json.dumps(merged_signals, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- SBTi TARGETS ---
    current_sbti = download_json_file(token, "YourLibrary/sbti_targets.json")
    new_sbti = []  # TODO: plug in newly scraped/updated target rows here
    merged_sbti = append_new_signals(current_sbti, new_sbti)  # same de-dupe logic works
    upload_json_file(token, "YourLibrary/sbti_targets.json", merged_sbti)
    SBTI_OUT.write_text(
        json.dumps(merged_sbti, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Wrote {len(merged_signals)} signals and {len(merged_sbti)} SBTi rows to {DEPLOY_DIR}")


if __name__ == "__main__":
    main()
