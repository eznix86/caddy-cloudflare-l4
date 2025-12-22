import os
import requests
import sys
import json
import uuid
import base64
from datetime import datetime, timezone

# --- Configuration ---
GITHUB_REPO = "caddyserver/caddy"
OFFICIAL_CADDY_IMAGE = "library/caddy"
# --- ghcr.io image path (owner/repo format) ---
GHCR_IMAGE_OWNER = os.environ.get('GITHUB_REPOSITORY_OWNER', "")
GHCR_IMAGE_NAME = os.environ.get('GITHUB_REPOSITORY', "").split('/')[-1] if os.environ.get('GITHUB_REPOSITORY') else "caddy-cloudflare-l4"
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', "")
# DEPRECATED !!! CHANGE THIS if your tags start with 'v' (e.g., use 'v') !!!
CUSTOM_TAG_PREFIX = ""
# These are the platforms WE want to build and require the OFFICIAL image to have available.
REQUIRED_PLATFORMS = {
    "linux/amd64",
    "linux/arm64",
    "linux/arm/v7",
    "linux/ppc64le",
    "linux/s390x",
}

def log_error(message):
    """Prints an error message formatted for GitHub Actions."""
    print(f"::error::ACTION_SCRIPT::{message}", file=sys.stderr)

def log_info(message):
    print(message, file=sys.stdout)

def set_action_output(output_name, value):
    """Sets the GitHub Action output using the GITHUB_OUTPUT environment file.
       Handles multiline values correctly.

    Args:
        output_name (str): The name of the output.
        value (any): The value of the output. Will be converted to string.
                     Multiline strings will be handled using delimiters.
    """
    if "GITHUB_OUTPUT" not in os.environ:
        print(f"::warning::GITHUB_OUTPUT environment variable not found. Cannot set output '{output_name}'.", file=sys.stderr)
        return

    output_path = os.environ["GITHUB_OUTPUT"]
    output_value = str(value) # Ensure value is a string

    try:
        with open(output_path, "a", encoding='utf-8') as f: # Specify encoding
            if '\n' in output_value:
                # Use heredoc syntax for multiline outputs
                delimiter = f"ghadelimiter_{uuid.uuid4()}" # Unique delimiter
                print(f"{output_name}<<{delimiter}", file=f)
                print(output_value, file=f)
                print(delimiter, file=f)
                # log_info(f"  Set multiline output '{output_name}' via GITHUB_OUTPUT") # Optional verbose log
            else:
                # Simple key=value for single line
                print(f"{output_name}={output_value}", file=f)
                # log_info(f"  Set output '{output_name}={output_value}' via GITHUB_OUTPUT") # Optional verbose log

    except OSError as e:
        log_error(f"Error writing to GITHUB_OUTPUT file at {output_path}: {e}")
        # Exiting might be safer if outputs are critical
        sys.exit(1)

def get_latest_caddy_release():
    """Fetches the latest release tag from the Caddy GitHub repository."""
    url = f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest'
    log_info(f"Fetching latest release from {url}")
    headers = {}
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'
        log_info("Using authenticated GitHub API request")
    else:
        log_info("::warning::No GITHUB_TOKEN found, using unauthenticated request (lower rate limit)")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        release = response.json()
        tag_name = release.get('tag_name')
        if not tag_name or not tag_name.startswith('v'):
             log_error(f"Invalid or missing 'tag_name' in GitHub release response: {tag_name}")
             sys.exit(1)
        log_info(f"Latest Caddy GitHub release tag found: {tag_name}")
        return tag_name
    except requests.exceptions.Timeout:
         log_error(f"Timeout fetching latest GitHub release from {url}")
         sys.exit(1)
    except requests.exceptions.HTTPError as e:
        log_error(f"HTTP Error fetching latest GitHub release: {e.response.status_code} {e}")
        if 400 <= e.response.status_code < 500: log_error(f"Response body: {e.response.text[:500]}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        log_error(f"Network error fetching latest GitHub release: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        log_error(f"Error decoding GitHub API JSON response: {e}")
        sys.exit(1)

def check_docker_hub_tag(image_name, tag):
    """Checks if a specific tag exists for a Docker Hub image. Returns tag data or None."""
    url = f"https://hub.docker.com/v2/repositories/{image_name}/tags/{tag}"
    try:
        response = requests.get(url, timeout=45)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            log_error(f"Unexpected status {response.status_code} checking Docker Hub tag '{tag}' for '{image_name}'. Response: {response.text[:200]}")
            return None
    except requests.exceptions.Timeout:
        log_error(f"Timeout checking Docker Hub tag '{tag}' for '{image_name}' at {url}")
        return None
    except requests.exceptions.RequestException as e:
        log_error(f"Network error checking Docker Hub tag '{tag}' for '{image_name}': {e}")
        return None
    except json.JSONDecodeError as e:
        log_error(f"Error decoding Docker Hub API response for tag '{tag}' of '{image_name}': {e}. Response: {response.text[:200]}")
        return None

def get_ghcr_token(owner, repo):
    """Gets an authentication token for ghcr.io registry."""
    # ghcr.io uses token-based auth via the token endpoint
    scope = f"repository:{owner.lower()}/{repo.lower()}:pull"
    token_url = f"https://ghcr.io/token?scope={scope}"

    headers = {}
    if GITHUB_TOKEN:
        # Use GITHUB_TOKEN for authentication to get registry token
        auth_string = base64.b64encode(f"token:{GITHUB_TOKEN}".encode()).decode()
        headers["Authorization"] = f"Basic {auth_string}"

    try:
        response = requests.get(token_url, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json().get('token')
        else:
            log_info(f"  Could not get ghcr.io token (status {response.status_code})")
            return None
    except Exception as e:
        log_info(f"  Error getting ghcr.io token: {e}")
        return None

def check_ghcr_tag(owner, repo, tag):
    """Checks if a specific tag exists for a ghcr.io image. Returns manifest data or None."""
    if not owner or not repo:
        log_error("GHCR owner or repo not configured")
        return None

    # First, get a registry token
    registry_token = get_ghcr_token(owner, repo)

    # ghcr.io uses the OCI distribution API
    url = f"https://ghcr.io/v2/{owner.lower()}/{repo.lower()}/manifests/{tag}"
    headers = {
        "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"
    }

    if registry_token:
        headers["Authorization"] = f"Bearer {registry_token}"

    try:
        response = requests.get(url, headers=headers, timeout=45)
        if response.status_code == 200:
            return response.json()
        elif response.status_code in (401, 403, 404):
            # 401/403/404 all mean "image not accessible" - treat as not found
            return None
        else:
            log_error(f"Unexpected status {response.status_code} checking ghcr.io tag '{tag}' for '{owner}/{repo}'. Response: {response.text[:200]}")
            return None
    except requests.exceptions.Timeout:
        log_error(f"Timeout checking ghcr.io tag '{tag}' for '{owner}/{repo}' at {url}")
        return None
    except requests.exceptions.RequestException as e:
        log_error(f"Network error checking ghcr.io tag '{tag}' for '{owner}/{repo}': {e}")
        return None
    except json.JSONDecodeError as e:
        log_error(f"Error decoding ghcr.io API response for tag '{tag}' of '{owner}/{repo}': {e}")
        return None

def get_platforms_from_ghcr_manifest(manifest_data):
    """Extracts required linux platform strings from ghcr.io manifest data."""
    platforms = set()
    if not manifest_data:
        return platforms

    # Handle OCI image index or Docker manifest list
    manifests = manifest_data.get('manifests', [])
    if not manifests:
        log_info("Could not find 'manifests' list in ghcr.io manifest data.")
        return platforms

    for manifest in manifests:
        if not isinstance(manifest, dict):
            continue
        platform = manifest.get('platform', {})
        os_name = platform.get('os')
        arch = platform.get('architecture')
        variant = platform.get('variant')

        if os_name != "linux" or not arch:
            continue

        platform_str = ""
        if arch == "arm" and variant == "v7":
            platform_str = f"{os_name}/{arch}/{variant}"
        elif f"{os_name}/{arch}" in REQUIRED_PLATFORMS:
            platform_str = f"{os_name}/{arch}"

        if platform_str in REQUIRED_PLATFORMS:
            platforms.add(platform_str)

    return platforms

def get_platforms_from_tag_data(tag_data):
    """Extracts required linux platform strings from Docker Hub tag API response."""
    platforms = set()
    if not tag_data or 'images' not in tag_data or not isinstance(tag_data['images'], list):
        log_info("Could not find valid 'images' list in Docker Hub tag data.")
        return platforms

    for img in tag_data['images']:
        if not isinstance(img, dict): continue
        os_name = img.get('os')
        arch = img.get('architecture')
        variant = img.get('variant')

        if os_name != "linux" or not arch: continue # Skip non-linux or invalid entries

        platform_str = ""
        if arch == "arm" and variant == "v7":
            platform_str = f"{os_name}/{arch}/{variant}"
        # Check against REQUIRED_PLATFORMS before constructing simple os/arch string
        elif f"{os_name}/{arch}" in REQUIRED_PLATFORMS:
             platform_str = f"{os_name}/{arch}"

        # Only add platform string if it matches one we require
        if platform_str in REQUIRED_PLATFORMS:
             platforms.add(platform_str)

    return platforms

def main():
    start_time = datetime.now(timezone.utc)
    log_info(f"--- Starting Caddy Check at {start_time.isoformat()} ---")

    if not REQUIRED_PLATFORMS:
        log_error("Configuration error: REQUIRED_PLATFORMS set is empty.")
        sys.exit(1)
    log_info(f"Required platforms: {REQUIRED_PLATFORMS}")

    latest_gh_tag = get_latest_caddy_release()
    official_docker_tag = latest_gh_tag.lstrip('v')
    custom_docker_tag = f"{CUSTOM_TAG_PREFIX}{official_docker_tag}"

    # 1. Check if the official Caddy image tag exists AND has required platforms
    log_info(f"Step 1: Checking official image '{OFFICIAL_CADDY_IMAGE}:{official_docker_tag}'...")
    official_image_data = check_docker_hub_tag(OFFICIAL_CADDY_IMAGE, official_docker_tag)
    official_image_ready = False
    if official_image_data:
        log_info(f"  Official tag '{official_docker_tag}' found. Verifying platforms...")
        found_official_platforms = get_platforms_from_tag_data(official_image_data)
        log_info(f"  Found official platforms relevant to requirements: {found_official_platforms or '{}'}")
        required_platforms_missing_in_official = REQUIRED_PLATFORMS - found_official_platforms

        if not required_platforms_missing_in_official:
            log_info(f"  Official image has all required platforms.")
            official_image_ready = True
        else:
            log_info(f"  Official image is MISSING required platforms: {required_platforms_missing_in_official}.")
    else:
        log_info(f"  Official Caddy image tag '{official_docker_tag}' not found.")

    # Exit if official image isn't ready
    if not official_image_ready:
        log_info("Result: Official image is not ready. No build triggered.")
        set_action_output('NEEDS_BUILD', 'false') 
        set_action_output('LATEST_VERSION', latest_gh_tag)
        sys.exit(0)

    # 2. Official image IS ready, check custom image status on ghcr.io
    ghcr_image = f"ghcr.io/{GHCR_IMAGE_OWNER}/{GHCR_IMAGE_NAME}".lower()
    log_info(f"Step 2: Checking custom image '{ghcr_image}:{custom_docker_tag}'...")
    custom_manifest_data = check_ghcr_tag(GHCR_IMAGE_OWNER, GHCR_IMAGE_NAME, custom_docker_tag)
    custom_image_complete = False

    if custom_manifest_data:
        log_info(f"  Custom image tag '{custom_docker_tag}' found on ghcr.io. Verifying platforms...")
        found_custom_platforms = get_platforms_from_ghcr_manifest(custom_manifest_data)
        log_info(f"  Found custom platforms relevant to requirements: {found_custom_platforms or '{}'}")
        required_platforms_missing_in_custom = REQUIRED_PLATFORMS - found_custom_platforms
        if not required_platforms_missing_in_custom:
            custom_image_complete = True
            log_info(f"  Custom image already exists and is complete.")
        else:
            log_info(f"  Custom image exists but is MISSING required platforms: {required_platforms_missing_in_custom}.")
    else:
        log_info(f"  Custom image tag '{custom_docker_tag}' NOT found on ghcr.io.")

    # 3. Decide if a build is needed (Official is ready AND custom is incomplete/missing)
    needs_build = not custom_image_complete

    log_info(f"Step 3: Final decision for Caddy {latest_gh_tag}: Needs build = {needs_build}")
    set_action_output('NEEDS_BUILD', 'true' if needs_build else 'false') 
    set_action_output('LATEST_VERSION', latest_gh_tag) 

    end_time = datetime.now(timezone.utc)
    log_info(f"--- Check finished at {end_time.isoformat()} (Duration: {end_time - start_time}) ---")

if __name__ == "__main__":
    main()
