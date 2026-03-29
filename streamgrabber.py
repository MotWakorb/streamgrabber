#!/usr/bin/env python3
"""
StreamGrabber - Xtream Codes API client and M3U parser that retrieves
all categories and their available streams, outputting to JSON or readable text.
"""

import argparse
import json
import re
import sys
import tty
import termios
import warnings
from collections import OrderedDict
from urllib.parse import urljoin, urlparse

warnings.filterwarnings("ignore", message=".*urllib3.*OpenSSL.*")

try:
    import requests
except ModuleNotFoundError:
    import subprocess
    print("Installing missing dependency: requests", file=sys.stderr)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests


def build_api_url(server_url, action=None, username=None, password=None, **params):
    """Build an Xtream Codes API URL."""
    base = server_url.rstrip("/")
    url = f"{base}/player_api.php"
    query = {"username": username, "password": password}
    if action:
        query["action"] = action
    query.update(params)
    return url, query


def authenticate(server_url, username, password):
    """Authenticate and return server/user info."""
    url, params = build_api_url(server_url, username=username, password=password)
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "user_info" not in data:
        raise RuntimeError("Authentication failed - no user_info in response.")

    user_info = data["user_info"]
    if user_info.get("auth") == 0 or str(user_info.get("status", "")).lower() != "active":
        raise RuntimeError(
            f"Authentication failed. Status: {user_info.get('status', 'unknown')}"
        )

    return data


def get_categories(server_url, username, password, stream_type):
    """
    Get categories for a stream type.
    stream_type: 'live', 'vod', or 'series'
    """
    action_map = {
        "live": "get_live_categories",
        "vod": "get_vod_categories",
        "series": "get_series_categories",
    }
    url, params = build_api_url(
        server_url, action=action_map[stream_type], username=username, password=password
    )
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json() or []


def get_streams(server_url, username, password, stream_type, category_id=None):
    """
    Get streams for a stream type, optionally filtered by category.
    stream_type: 'live', 'vod', or 'series'
    """
    action_map = {
        "live": "get_live_streams",
        "vod": "get_vod_streams",
        "series": "get_series",
    }
    extra = {}
    if category_id is not None:
        extra["category_id"] = category_id

    url, params = build_api_url(
        server_url,
        action=action_map[stream_type],
        username=username,
        password=password,
        **extra,
    )
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json() or []


def gather_all(server_url, username, password, stream_types=None):
    """Gather all categories and streams, grouped by type and category."""
    if stream_types is None:
        stream_types = ["live", "vod", "series"]

    result = {}

    for stype in stream_types:
        print(f"  Fetching {stype} categories...", file=sys.stderr)
        categories = get_categories(server_url, username, password, stype)
        type_data = []

        for cat in categories:
            cat_id = cat.get("category_id")
            cat_name = cat.get("category_name", f"Unknown ({cat_id})")
            print(f"    [{stype}] {cat_name} ...", file=sys.stderr)

            streams = get_streams(server_url, username, password, stype, cat_id)
            stream_list = []
            for s in streams:
                entry = {
                    "name": s.get("name") or s.get("title", "Unknown"),
                    "stream_id": s.get("stream_id") or s.get("series_id"),
                }
                if stype == "live":
                    entry["epg_channel_id"] = s.get("epg_channel_id", "")
                    entry["stream_icon"] = s.get("stream_icon", "")
                elif stype == "vod":
                    entry["stream_icon"] = s.get("stream_icon", "")
                    entry["rating"] = s.get("rating", "")
                    entry["container_extension"] = s.get("container_extension", "")
                elif stype == "series":
                    entry["cover"] = s.get("cover", "")
                    entry["rating"] = s.get("rating", "")
                    entry["last_modified"] = s.get("last_modified", "")

                stream_list.append(entry)

            type_data.append(
                {
                    "category_id": cat_id,
                    "category_name": cat_name,
                    "stream_count": len(stream_list),
                    "streams": stream_list,
                }
            )

        result[stype] = {
            "total_categories": len(type_data),
            "total_streams": sum(g["stream_count"] for g in type_data),
            "categories": type_data,
        }

    return result


def parse_extinf(line):
    """Parse a #EXTINF line into its attributes and display name."""
    attrs = {}
    # Extract key="value" pairs from the EXTINF line
    for match in re.finditer(r'([\w-]+)="([^"]*)"', line):
        attrs[match.group(1)] = match.group(2)
    # Display name is everything after the last comma
    comma_pos = line.rfind(",")
    if comma_pos != -1:
        attrs["_name"] = line[comma_pos + 1:].strip()
    else:
        attrs["_name"] = "Unknown"
    return attrs


def detect_stream_type(url):
    """Detect stream type from URL path patterns."""
    path = urlparse(url).path.lower()
    if "/movie/" in path or "/movies/" in path:
        return "vod"
    if "/series/" in path:
        return "series"
    return "live"


def guess_type_from_extension(url):
    """Guess stream type from file extension as a fallback."""
    path = urlparse(url).path.lower()
    if path.endswith((".ts", ".m3u8")):
        return "live"
    if path.endswith((".mp4", ".mkv", ".avi")):
        return "vod"
    return "live"


def parse_m3u(source, dedupe=False):
    """
    Parse an M3U file or URL into the same structure as gather_all().
    Groups streams by group-title, detects stream type from URL patterns.
    If dedupe is True, duplicate URLs are skipped (first occurrence wins).
    """
    if source.startswith(("http://", "https://")):
        print(f"  Downloading M3U from URL...", file=sys.stderr)
        resp = requests.get(source, timeout=60)
        resp.raise_for_status()
        content = resp.text
    else:
        print(f"  Reading M3U file: {source}", file=sys.stderr)
        with open(source, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

    lines = content.splitlines()
    if not lines or not lines[0].strip().startswith("#EXTM3U"):
        print("Warning: file does not start with #EXTM3U header", file=sys.stderr)

    # Parse entries: each entry is an EXTINF line followed by a URL line
    # Group by (stream_type, group-title)
    # Use OrderedDict to preserve category order as they appear in the file
    groups = {}  # (type, group_title) -> list of stream entries
    group_order = []  # track insertion order of (type, group_title)

    attrs = None
    total_parsed = 0
    total_original = 0
    seen_urls = set()
    dupes_skipped = 0
    group_original_counts = {}  # (type, group_title) -> original count before dedup
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#EXTM3U"):
            continue
        if line.startswith("#EXTINF"):
            attrs = parse_extinf(line)
            continue
        if line.startswith("#"):
            continue

        # This is a URL line
        url = line
        if attrs is None:
            attrs = {"_name": url.split("/")[-1] or "Unknown"}

        # Detect stream type and group for every entry (including dupes)
        stype = detect_stream_type(url)
        if stype == "live":
            stype = guess_type_from_extension(url)
        group = attrs.get("group-title", "Uncategorized")
        key = (stype, group)

        total_original += 1
        if dedupe:
            group_original_counts[key] = group_original_counts.get(key, 0) + 1
            # Track group order even for fully-deduped groups
            if key not in groups:
                groups[key] = []
                group_order.append(key)

        if dedupe and url in seen_urls:
            dupes_skipped += 1
            attrs = None
            continue
        if dedupe:
            seen_urls.add(url)

        if key not in groups:
            groups[key] = []
            group_order.append(key)

        entry = {
            "name": attrs.get("_name", "Unknown"),
            "url": url,
        }
        # Include relevant metadata based on type
        if stype == "live":
            entry["epg_channel_id"] = attrs.get("tvg-id", "")
            entry["stream_icon"] = attrs.get("tvg-logo", "")
        elif stype == "vod":
            entry["stream_icon"] = attrs.get("tvg-logo", "")
            ext = url.rsplit(".", 1)[-1] if "." in url.split("/")[-1] else ""
            entry["container_extension"] = ext
        elif stype == "series":
            entry["stream_icon"] = attrs.get("tvg-logo", "")

        groups[key].append(entry)
        total_parsed += 1
        attrs = None

    if dedupe and dupes_skipped:
        print(f"  Removed {dupes_skipped} duplicate URLs", file=sys.stderr)
    print(f"  Parsed {total_parsed} streams", file=sys.stderr)

    # Build output structure identical to gather_all()
    result = {}
    cat_counter = {}  # auto-increment category IDs per type

    for stype, group_title in group_order:
        if stype not in result:
            result[stype] = {
                "total_categories": 0,
                "total_streams": 0,
                "categories": [],
            }
            cat_counter[stype] = 1

        stream_list = groups[(stype, group_title)]
        # Add stream_id based on position
        for i, entry in enumerate(stream_list, 1):
            entry["stream_id"] = i

        cat_entry = {
            "category_id": str(cat_counter[stype]),
            "category_name": group_title,
            "stream_count": len(stream_list),
            "streams": stream_list,
        }
        if dedupe:
            original = group_original_counts.get((stype, group_title), len(stream_list))
            cat_entry["original_stream_count"] = original

        result[stype]["categories"].append(cat_entry)
        cat_counter[stype] += 1

    # Update totals
    for stype in result:
        cats = result[stype]["categories"]
        result[stype]["total_categories"] = len(cats)
        result[stype]["total_streams"] = sum(c["stream_count"] for c in cats)
        if dedupe:
            result[stype]["original_total_streams"] = sum(
                c["original_stream_count"] for c in cats
            )

    return result


def write_json(data, output_path):
    """Write data as JSON."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"JSON output written to: {output_path}", file=sys.stderr)


def write_text(data, output_path):
    """Write data as human-readable text."""
    with open(output_path, "w", encoding="utf-8") as f:
        for stype, type_info in data.items():
            header = stype.upper()
            f.write(f"{'=' * 60}\n")
            f.write(f"  {header} STREAMS\n")
            if "original_total_streams" in type_info:
                f.write(
                    f"  Categories: {type_info['total_categories']}  |  "
                    f"Original: {type_info['original_total_streams']}  |  "
                    f"After Dedup: {type_info['total_streams']}\n"
                )
            else:
                f.write(
                    f"  Categories: {type_info['total_categories']}  |  "
                    f"Total Streams: {type_info['total_streams']}\n"
                )
            f.write(f"{'=' * 60}\n\n")

            for group in type_info["categories"]:
                if "original_stream_count" in group:
                    f.write(
                        f"--- {group['category_name']} "
                        f"(original: {group['original_stream_count']}, "
                        f"deduped: {group['stream_count']}) ---\n"
                    )
                else:
                    f.write(f"--- {group['category_name']} ({group['stream_count']} streams) ---\n")
                for i, stream in enumerate(group["streams"], 1):
                    f.write(f"  {i:>4}. {stream['name']}\n")
                f.write("\n")

            f.write("\n")

    print(f"Text output written to: {output_path}", file=sys.stderr)


def input_password(prompt="Password: "):
    """Read password input, displaying * for each character."""
    sys.stderr.write(prompt)
    sys.stderr.flush()
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    password = []
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                sys.stderr.write("\n")
                break
            elif ch in ("\x7f", "\x08"):  # backspace / delete
                if password:
                    password.pop()
                    sys.stderr.write("\b \b")
            elif ch == "\x03":  # Ctrl-C
                sys.stderr.write("\n")
                raise KeyboardInterrupt
            else:
                password.append(ch)
                sys.stderr.write("*")
            sys.stderr.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return "".join(password)


def prompt_stream_types():
    """Interactively prompt the user to select stream types."""
    options = ["live", "vod", "series"]
    print("\nSelect stream types to fetch:", file=sys.stderr)
    for i, opt in enumerate(options, 1):
        print(f"  [{i}] {opt}", file=sys.stderr)
    print(f"  [a] all", file=sys.stderr)
    print(file=sys.stderr)

    while True:
        choice = input("Enter choices (e.g. 1,3 or a): ").strip().lower()
        if choice == "a" or choice == "":
            return list(options)
        selected = []
        valid = True
        for part in choice.replace(" ", ",").split(","):
            part = part.strip()
            if not part:
                continue
            if part in ("1", "2", "3"):
                selected.append(options[int(part) - 1])
            elif part in options:
                selected.append(part)
            else:
                print(f"  Invalid choice: {part}", file=sys.stderr)
                valid = False
                break
        if valid and selected:
            # Remove duplicates while preserving order
            seen = set()
            unique = []
            for s in selected:
                if s not in seen:
                    seen.add(s)
                    unique.append(s)
            return unique
        if valid:
            print("  Please select at least one type.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="StreamGrabber - Retrieve all categories and streams from an Xtream Codes server or M3U playlist.",
        epilog=(
            "examples:\n"
            "  %(prog)s http://example.com:8080 -u user -p pass\n"
            "  %(prog)s http://example.com:8080 -u user -p pass -t live vod\n"
            "  %(prog)s -m playlist.m3u\n"
            "  %(prog)s -m http://example.com/get.php?username=user&password=pass&type=m3u_plus\n"
            "  %(prog)s -m playlist.m3u -d\n"
            "  %(prog)s -m playlist.m3u -f text -o streams.txt\n"
            "  %(prog)s                (run with no arguments for interactive prompts)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", nargs="?", default=None, help="server URL (e.g. http://example.com:8080)")
    parser.add_argument("-m", default=None, metavar="M3U",
                        help="M3U file path or URL (skips XC API, parses playlist directly)")
    parser.add_argument("-d", action="store_true",
                        help="deduplicate streams by URL (M3U mode only, keeps first occurrence)")
    parser.add_argument("-u", default=None, metavar="USER", help="account username")
    parser.add_argument("-p", default=None, metavar="PASS", help="account password")
    parser.add_argument("-t", nargs="+", choices=["live", "vod", "series"], default=None,
                        metavar="TYPE", help="stream types to fetch: live, vod, series (default: prompt)")
    parser.add_argument("-f", choices=["json", "text"], default="json", metavar="FMT",
                        help="output format: json or text (default: json)")
    parser.add_argument("-o", default="streams_output.json", metavar="FILE",
                        help="output file path (default: streams_output.json)")
    args = parser.parse_args()

    if args.m:
        # M3U mode
        print("Parsing M3U playlist...", file=sys.stderr)
        try:
            data = parse_m3u(args.m, dedupe=args.d)
        except requests.RequestException as e:
            print(f"Download error: {e}", file=sys.stderr)
            sys.exit(1)
        except (OSError, IOError) as e:
            print(f"File error: {e}", file=sys.stderr)
            sys.exit(1)

        # Filter by stream types if specified
        if args.t:
            data = {k: v for k, v in data.items() if k in args.t}
    else:
        # Xtream Codes API mode
        if args.url is None:
            args.url = input("Server URL: ").strip()
        if args.u is None:
            args.u = input("Username: ").strip()
        if args.p is None:
            args.p = input_password()
        if args.t is None:
            args.t = prompt_stream_types()

        print("Authenticating...", file=sys.stderr)
        try:
            auth_data = authenticate(args.url, args.u, args.p)
        except requests.RequestException as e:
            print(f"Connection error: {e}", file=sys.stderr)
            sys.exit(1)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        user = auth_data["user_info"]
        print(
            f"Logged in as: {user.get('username')} | "
            f"Status: {user.get('status')} | "
            f"Expires: {user.get('exp_date', 'N/A')}",
            file=sys.stderr,
        )

        print("Fetching streams...", file=sys.stderr)
        data = gather_all(args.url, args.u, args.p, args.t)

    if args.f == "json":
        write_json(data, args.o)
    else:
        write_text(data, args.o)

    # Summary
    for stype, info in data.items():
        if "original_total_streams" in info:
            print(
                f"  {stype}: {info['total_categories']} categories, "
                f"{info['original_total_streams']} original -> "
                f"{info['total_streams']} after dedup",
                file=sys.stderr,
            )
        else:
            print(
                f"  {stype}: {info['total_categories']} categories, "
                f"{info['total_streams']} streams",
                file=sys.stderr,
            )
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
