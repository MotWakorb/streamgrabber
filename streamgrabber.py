#!/usr/bin/env python3
"""
StreamGrabber - Xtream Codes API client that retrieves all categories
and their available streams, outputting to JSON or readable text.
"""

import argparse
import json
import sys
import tty
import termios
import warnings
from urllib.parse import urljoin

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
            f.write(
                f"  Categories: {type_info['total_categories']}  |  "
                f"Total Streams: {type_info['total_streams']}\n"
            )
            f.write(f"{'=' * 60}\n\n")

            for group in type_info["categories"]:
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
        description="StreamGrabber - Retrieve all categories and streams from an Xtream Codes server.",
        epilog=(
            "examples:\n"
            "  %(prog)s http://example.com:8080 -u user -p pass\n"
            "  %(prog)s http://example.com:8080 -u user -p pass -t live vod\n"
            "  %(prog)s http://example.com:8080 -u user -p pass -f text -o streams.txt\n"
            "  %(prog)s                (run with no arguments for interactive prompts)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", nargs="?", default=None, help="server URL (e.g. http://example.com:8080)")
    parser.add_argument("-u", default=None, metavar="USER", help="account username")
    parser.add_argument("-p", default=None, metavar="PASS", help="account password")
    parser.add_argument("-t", nargs="+", choices=["live", "vod", "series"], default=None,
                        metavar="TYPE", help="stream types to fetch: live, vod, series (default: prompt)")
    parser.add_argument("-f", choices=["json", "text"], default="json", metavar="FMT",
                        help="output format: json or text (default: json)")
    parser.add_argument("-o", default="streams_output.json", metavar="FILE",
                        help="output file path (default: streams_output.json)")
    args = parser.parse_args()

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
        print(
            f"  {stype}: {info['total_categories']} categories, "
            f"{info['total_streams']} streams",
            file=sys.stderr,
        )
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
