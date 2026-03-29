# StreamGrabber

A command-line tool that retrieves all categories and streams from an Xtream Codes server or M3U playlist and saves them to a JSON or text file.

## Requirements

- Python 3.6+
- `requests` (installed automatically on first run if missing)

## Usage

Run with no arguments for interactive prompts:

```
python streamgrabber.py
```

You'll be prompted for the server URL, username, password (masked), and which stream types to fetch.

Or pass everything on the command line:

```
python streamgrabber.py http://example.com:8080 -u myuser -p mypass
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `url` | Server URL (positional, for XC API mode) | prompt |
| `-m M3U` | M3U file path or URL (skips XC API) | |
| `-d` | Deduplicate streams by URL (M3U mode, keeps first) | off |
| `-u USER` | Account username (XC API mode) | prompt |
| `-p PASS` | Account password (XC API mode) | prompt (masked) |
| `-t TYPE [...]` | Stream types: `live`, `vod`, `series` | prompt / all |
| `-f FMT` | Output format: `json` or `text` | `json` |
| `-o FILE` | Output file path | `streams_output.json` |
| `-h` | Show help message | |

### Examples

**Xtream Codes API mode:**

```
python streamgrabber.py http://example.com:8080 -u user -p pass
python streamgrabber.py http://example.com:8080 -u user -p pass -t live vod
```

**M3U mode** (local file or URL):

```
python streamgrabber.py -m playlist.m3u
python streamgrabber.py -m playlist.m3u -d
python streamgrabber.py -m http://example.com/get.php?username=user&password=pass&type=m3u_plus
python streamgrabber.py -m playlist.m3u -t live -f text -o streams.txt
```

Output as human-readable text:

```
python streamgrabber.py http://example.com:8080 -u user -p pass -f text -o streams.txt
```

## Output

### JSON format (default)

```json
{
  "live": {
    "total_categories": 50,
    "total_streams": 1200,
    "categories": [
      {
        "category_id": "1",
        "category_name": "Sports",
        "stream_count": 45,
        "streams": [
          {
            "name": "ESPN HD",
            "stream_id": 101,
            "epg_channel_id": "espn.us",
            "stream_icon": "http://..."
          }
        ]
      }
    ]
  },
  "vod": { ... },
  "series": { ... }
}
```

### Text format

```
============================================================
  LIVE STREAMS
  Categories: 50  |  Total Streams: 1200
============================================================

--- Sports (45 streams) ---
     1. ESPN HD
     2. Fox Sports 1
     ...
```

## M3U parsing

When using `-m`, StreamGrabber parses extended M3U playlists (`#EXTM3U` / `#EXTINF`) and produces the same grouped output as the XC API mode:

- Streams are grouped by the `group-title` attribute into categories
- Stream type is auto-detected from URL patterns (`/live/`, `/movie/`, `/series/`) and file extensions
- EPG channel IDs come from `tvg-id`, icons from `tvg-logo`
- Works with both local `.m3u` / `.m3u8` files and remote URLs
- Use `-t` to filter to specific stream types after parsing
- Use `-d` to deduplicate streams by URL (first occurrence is kept, duplicates in later categories are removed)

## Stream type fields

Each stream type includes different metadata:

**XC API mode:**

- **live** - `name`, `stream_id`, `epg_channel_id`, `stream_icon`
- **vod** - `name`, `stream_id`, `stream_icon`, `rating`, `container_extension`
- **series** - `name`, `stream_id`, `cover`, `rating`, `last_modified`

**M3U mode:**

- **live** - `name`, `stream_id`, `url`, `epg_channel_id`, `stream_icon`
- **vod** - `name`, `stream_id`, `url`, `stream_icon`, `container_extension`
- **series** - `name`, `stream_id`, `url`, `stream_icon`
