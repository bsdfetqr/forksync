import requests, time, os, sys

# Configuration
TOKEN = os.getenv("GH_TOKEN")
STATE_FILE = "last_repo.txt"
ERROR_FILE = "error_repos.md"
START_TIME = time.time()
MAX_RUNTIME = 5.2 * 3600  # 5.2 hours to be safe
HEADERS = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}

def get_last_synced():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return f.read().strip()
    return None

def log_error(repo_name, status_code, message):
    mode = "a" if os.path.exists(ERROR_FILE) else "w"
    with open(ERROR_FILE, mode) as f:
        if mode == "w":
            f.write("# ❌ Sync Error Log\n\n")
        f.write(f"- **{repo_name}**: HTTP {status_code} - {message}\n")

def sync_all():
    last_synced = get_last_synced()
    found_start_point = last_synced is None
    page = 1
    total_synced_this_run = 0

    while True:
        resp = requests.get(f"https://api.github.com/user/repos?type=owner&per_page=100&page={page}", headers=HEADERS)
        repos = resp.json()
        if not repos or "message" in repos: break

        for repo in repos:
            # Time limit check
            if (time.time() - START_TIME) > MAX_RUNTIME:
                print(f"⏰ Time limit approaching. Managed to sync {total_synced_this_run} repos this run.")
                sys.exit(0)

            if not repo.get('fork'): continue
            
            name = repo['full_name']

            # Resume logic
            if not found_start_point:
                if name == last_synced:
                    found_start_point = True
                continue

            # API Sync Call
            print(f"🔄 Syncing {name}...")
            sync_url = f"https://api.github.com/repos/{name}/merge-upstream"
            sync_resp = requests.post(sync_url, headers=HEADERS, json={"branch": repo['default_branch']})
            
            if sync_resp.status_code == 409:
                log_error(name, 409, "Merge Conflict (Manual sync required)")
            elif sync_resp.status_code not in [200, 422]:
                log_error(name, sync_resp.status_code, sync_resp.text)
            
            # Always update the checkpoint to the current repo (even if it errored)
            # so we don't get stuck on a broken repo forever.
            with open(STATE_FILE, "w") as f:
                f.write(name)
            
            total_synced_this_run += 1

            # Rate limit handling
            remaining = int(sync_resp.headers.get("X-RateLimit-Remaining", 1))
            if remaining < 10:
                reset_time = int(sync_resp.headers.get("X-RateLimit-Reset", time.time() + 3600))
                sleep_duration = max(reset_time - time.time() + 5, 0)
                print(f"⚠️ Rate limit low. Sleeping for {int(sleep_duration/60)} minutes...")
                time.sleep(sleep_duration)

        page += 1
    
    # SUCCESS: If the loop finishes naturally, everything is done.
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    print("✅ Full sync cycle complete.")

if __name__ == "__main__":
    sync_all()
