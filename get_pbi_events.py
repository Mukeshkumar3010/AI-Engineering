"""
Power BI Activity Events Extractor
Retrieves audit logs from Power BI Admin API and exports to JSON and CSV.
"""

import requests
import msal
import json
import csv
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, unquote
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")

if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID]):
    raise ValueError("Missing required environment variables. Please check your .env file.")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]


def get_access_token():
    """Get access token using MSAL."""
    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )
    
    result = app.acquire_token_for_client(scopes=SCOPE)
    
    if "access_token" in result:
        return result["access_token"]
    else:
        raise Exception(f"Failed to get token: {result.get('error_description')}")


def get_activity_events(access_token, start_datetime, end_datetime):
    """
    Get Power BI activity events for a specific time range.
    
    Args:
        access_token: Azure AD access token
        start_datetime: Start datetime in ISO 8601 format (e.g., '2025-12-16T00:00:00.000Z')
        end_datetime: End datetime in ISO 8601 format (e.g., '2025-12-16T23:59:59.999Z')
                      Must be within the same UTC day as start_datetime
    
    Returns:
        List of activity events
    """
    base_url = "https://api.powerbi.com/v1.0/myorg/admin/activityevents"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    all_events = []
    continuation_uri = None
    continuation_token = None
    seen_tokens = set()
    iteration = 0
    
    # Initial call with dates (must be single-quoted)
    iteration += 1
    params = {
        "startDateTime": f"'{start_datetime}'",
        "endDateTime": f"'{end_datetime}'"
    }
    
    print(f"\n📡 [Page {iteration}] Initial API request")
    
    response = requests.get(base_url, headers=headers, params=params, timeout=60)
    
    if response.status_code != 200:
        raise Exception(f"API request failed: {response.status_code} - {response.text}")
    
    data = response.json()
    events = data.get("activityEventEntities") or data.get("activityEvents") or []
    all_events.extend(events)
    print(f"   ✅ Retrieved {len(events)} events | Total: {len(all_events)}")
    
    continuation_uri = data.get("continuationUri")
    continuation_token = data.get("continuationToken")
    
    if continuation_uri:
        print(f"   🔗 Continuation URI available")
    
    # Continue with pagination
    while continuation_uri or continuation_token:
        iteration += 1
        
        if continuation_uri:
            print(f"\n📡 [Page {iteration}] Fetching next page via URI")
            response = requests.get(continuation_uri, headers=headers, timeout=60)
        else:
            print(f"\n📡 [Page {iteration}] Fetching next page via token")
            token_norm = quote(unquote(continuation_token), safe="")
            params = {"continuationToken": f"'{token_norm}'"}
            response = requests.get(base_url, headers=headers, params=params, timeout=60)
        
        if response.status_code != 200:
            raise Exception(f"API request failed: {response.status_code} - {response.text}")
        
        data = response.json()
        events = data.get("activityEventEntities") or data.get("activityEvents") or []
        all_events.extend(events)
        print(f"   ✅ Retrieved {len(events)} events | Total: {len(all_events)}")
        
        next_uri = data.get("continuationUri")
        next_token = data.get("continuationToken")
        
        if next_token and next_token in seen_tokens:
            print(f"   ⚠️  Repeated token detected - stopping")
            break
        
        if continuation_token:
            seen_tokens.add(continuation_token)
        
        continuation_uri = next_uri
        continuation_token = next_token
        
        if not continuation_uri and not continuation_token:
            print(f"   ✅ No more pages available")
            break
    
    return all_events


def export_to_csv(events, filepath):
    """Export events to CSV file with proper quoting to handle commas in text fields."""
    if not events:
        return
    
    # Get all unique keys from all events
    all_keys = set()
    for event in events:
        all_keys.update(event.keys())
    
    fieldnames = sorted(all_keys)
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
        writer.writeheader()
        writer.writerows(events)


def main():
    """Main function to retrieve and display Power BI events."""
    try:
        print("=" * 80)
        print("🔷 Power BI Activity Events Extractor")
        print("=" * 80)
        
        print("\n🔐 Authenticating...")
        token = get_access_token()
        print("   ✅ Access token obtained")
        
        # Get events for yesterday (must be within same UTC day)
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)
        
        start_datetime = f"{yesterday}T00:00:00.000Z"
        end_datetime = f"{yesterday}T23:59:59.999Z"
        
        print(f"\n📅 Date range: {yesterday} (Full UTC day)")
        print(f"   ⏰ Start: {start_datetime}")
        print(f"   ⏰ End:   {end_datetime}")
        
        events = get_activity_events(token, start_datetime, end_datetime)
        
        print(f"\n📊 Total events retrieved: {len(events)}")
        
        if not events:
            print("   ⚠️  No events found for this date range")
            return
        
        # Create files subfolder
        files_dir = Path("files")
        files_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_filename = f"pbi_events_{yesterday}"
        
        # Save to JSON
        json_file = files_dir / f"{base_filename}_{timestamp}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        print(f"\n💾 JSON saved: {json_file}")
        
        # Save to CSV
        csv_file = files_dir / f"{base_filename}_{timestamp}.csv"
        export_to_csv(events, csv_file)
        print(f"💾 CSV saved:  {csv_file}")
        
        # Event type summary
        event_types = {}
        for event in events:
            event_type = event.get("Activity", "Unknown")
            event_types[event_type] = event_types.get(event_type, 0) + 1
        
        print(f"\n📈 Activity Summary (Top 10):")
        for event_type, count in sorted(event_types.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   • {event_type}: {count}")
        
        print("\n" + "=" * 80)
        print("✅ Extraction completed successfully!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        print("=" * 80)


if __name__ == "__main__":
    main()
