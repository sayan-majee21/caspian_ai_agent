"""GitHub Repository Inspection Service for TalentCaspian Agent 1.

Fetches metadata, README, repository file tree, and key source code files
asynchronously using httpx and authenticated GitHub REST API calls.
"""

import logging
import os
import re
from typing import Any
import httpx

logger = logging.getLogger("talentcaspian.github_service")

# Priority source extensions to scan
SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cpp", ".c", ".h",
    ".go", ".rs", ".html", ".css", ".sql", ".json", ".md", ".sh", ".yml", ".yaml"
}

# Directories and files to ignore during tree scan
IGNORE_PATTERNS = [
    r"^\.git/", r"^node_modules/", r"^venv/", r"^\.venv/", r"^dist/", r"^build/",
    r"\.min\.js$", r"\.min\.css$", r"package-lock\.json$", r"yarn\.lock$", r"pnpm-lock\.yaml$"
]


def parse_github_url(repo_url: str) -> tuple[str, str]:
    """Parse a GitHub repository URL or handle into owner and repo names.

    Args:
        repo_url (str): Repository URL (HTTPS/SSH) or 'owner/repo' string.

    Returns:
        tuple[str, str]: (owner, repo) tuple.

    Raises:
        ValueError: If repository URL format is invalid.
    """
    clean = repo_url.strip().rstrip("/")
    if clean.endswith(".git"):
        clean = clean[:-4]

    # Handle https://github.com/owner/repo or http://...
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+)", clean, re.IGNORECASE)
    if match:
        return match.group(1), match.group(2)

    # Handle raw 'owner/repo' string
    parts = [p for p in clean.split("/") if p]
    if len(parts) == 2 and not clean.startswith("http"):
        return parts[0], parts[1]

    raise ValueError(f"Invalid GitHub repository URL or format: {repo_url}")


def get_auth_headers(token: str | None = None) -> dict[str, str]:
    """Construct HTTP headers for GitHub API request.

    Args:
        token (str | None): GitHub API token.

    Returns:
        dict[str, str]: Header dictionary.
    """
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "TalentCaspian-Agent1",
    }
    tok = token or os.getenv("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    return headers


async def fetch_repo_metadata(
    owner: str, repo: str, token: str | None = None
) -> dict[str, Any]:
    """Fetch repository metadata from GitHub REST API.

    Args:
        owner (str): Repository owner.
        repo (str): Repository name.
        token (str | None): GitHub API token.

    Returns:
        dict[str, Any]: Metadata JSON dictionary.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.get(url, headers=get_auth_headers(token))
        if res.status_code == 404:
            raise ValueError(f"GitHub repository not found: {owner}/{repo}")
        elif res.status_code == 403:
            logger.warning(f"GitHub rate limit exceeded for {owner}/{repo}")
            raise RuntimeError("GitHub API rate limit exceeded")
        res.raise_for_status()
        return res.json()


async def fetch_readme_content(
    owner: str, repo: str, token: str | None = None
) -> str:
    """Fetch raw README.md content from repository.

    Args:
        owner (str): Repository owner.
        repo (str): Repository name.
        token (str | None): GitHub API token.

    Returns:
        str: Raw README text, or empty string if not found.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    headers = get_auth_headers(token)
    headers["Accept"] = "application/vnd.github.v3.raw"
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.get(url, headers=headers)
        if res.status_code == 200:
            return res.text
        return ""


async def fetch_repository_tree(
    owner: str, repo: str, default_branch: str = "main", token: str | None = None
) -> list[dict[str, Any]]:
    """Fetch entire git tree recursively for default branch.

    Args:
        owner (str): Repository owner.
        repo (str): Repository name.
        default_branch (str): Default branch name (e.g. main/master).
        token (str | None): GitHub API token.

    Returns:
        list[dict[str, Any]]: List of tree item objects.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.get(url, headers=get_auth_headers(token))
        if res.status_code == 200:
            data = res.json()
            return data.get("tree", [])
        return []


def is_ignored_path(path: str) -> bool:
    """Check if a file path should be ignored during inspection.

    Args:
        path (str): Relative file path.

    Returns:
        bool: True if path should be ignored.
    """
    for pattern in IGNORE_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            return True
    return False


async def fetch_source_files(
    owner: str,
    repo: str,
    tree: list[dict[str, Any]],
    default_branch: str = "main",
    max_files: int = 15,
    max_file_size_bytes: int = 50 * 1024,
    token: str | None = None,
) -> dict[str, str]:
    """Fetch contents of key source files from repository up to limits.

    Args:
        owner (str): Repository owner.
        repo (str): Repository name.
        tree (list[dict[str, Any]]): Repository tree entries.
        default_branch (str): Branch name.
        max_files (int): Maximum number of files to download.
        max_file_size_bytes (int): Maximum size per file (bytes).
        token (str | None): GitHub API token.

    Returns:
        dict[str, str]: Dictionary mapping relative path to string content.
    """
    candidate_paths: list[str] = []
    for item in tree:
        if item.get("type") == "blob":
            path = item.get("path", "")
            if is_ignored_path(path):
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext in SOURCE_EXTENSIONS:
                candidate_paths.append(path)

    # Sort files prioritizing root/core files
    def score_path(p: str) -> int:
        base = os.path.basename(p).lower()
        if base in ("main.py", "app.py", "index.js", "index.ts", "server.js", "manage.py"):
            return 0
        depth = p.count("/")
        return 10 + depth

    candidate_paths.sort(key=score_path)
    selected_paths = candidate_paths[:max_files]

    source_files: dict[str, str] = {}
    headers = get_auth_headers(token)
    headers["Accept"] = "application/vnd.github.v3.raw"

    async with httpx.AsyncClient(timeout=10.0) as client:
        for path in selected_paths:
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{path}"
            try:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    text = res.text
                    if len(text.encode("utf-8")) > max_file_size_bytes:
                        text = text[:max_file_size_bytes] + "\n...[truncated]"
                    source_files[path] = text
                else:
                    # Fallback to GitHub API contents endpoint
                    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={default_branch}"
                    res_api = await client.get(api_url, headers=headers)
                    if res_api.status_code == 200:
                        text = res_api.text
                        if len(text.encode("utf-8")) > max_file_size_bytes:
                            text = text[:max_file_size_bytes] + "\n...[truncated]"
                        source_files[path] = text
            except Exception as exc:
                logger.warning(f"Failed to fetch file {path} from {owner}/{repo}: {exc}")

    return source_files


async def scan_github_repository(
    repo_url: str, token: str | None = None
) -> dict[str, Any]:
    """Scrape and aggregate full inspection payload for a GitHub repository.

    Args:
        repo_url (str): Repository URL or handle.
        token (str | None): Optional GitHub API token.

    Returns:
        dict[str, Any]: Deep inspection payload containing metadata, README,
        tree structure, and key source code snippets.
    """
    owner, repo = parse_github_url(repo_url)
    metadata = await fetch_repo_metadata(owner, repo, token=token)
    default_branch = metadata.get("default_branch", "main")

    readme_text = await fetch_readme_content(owner, repo, token=token)
    tree = await fetch_repository_tree(owner, repo, default_branch=default_branch, token=token)

    tree_paths = [item["path"] for item in tree if item.get("type") == "blob" and not is_ignored_path(item.get("path", ""))]
    source_files = await fetch_source_files(
        owner, repo, tree, default_branch=default_branch, token=token
    )

    return {
        "owner": owner,
        "repo": repo,
        "repo_url": repo_url,
        "stars": metadata.get("stargazers_count", 0),
        "forks": metadata.get("forks_count", 0),
        "language": metadata.get("language", "Unknown"),
        "description": metadata.get("description", ""),
        "default_branch": default_branch,
        "readme": readme_text,
        "tree_structure": tree_paths[:100],
        "source_files": source_files,
    }
