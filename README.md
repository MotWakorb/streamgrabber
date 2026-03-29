# StreamGrabber

A command-line tool that retrieves all categories and streams from an Xtream Codes server and saves them to a JSON or text file.

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
| `url` | Server URL (positional) | prompt |
| `-u USER` | Account username | prompt |
| `-p PASS` | Account password | prompt (masked) |
| `-t TYPE [...]` | Stream types: `live`, `vod`, `series` | prompt |
| `-f FMT` | Output format: `json` or `text` | `json` |
| `-o FILE` | Output file path | `streams_output.json` |
| `-h` | Show help message | |

### Examples

Fetch all stream types:

```
python streamgrabber.py http://example.com:8080 -u user -p pass
```

Fetch only live and VOD:

```
python streamgrabber.py http://example.com:8080 -u user -p pass -t live vod
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

## Stream type fields

Each stream type includes different metadata:

- **live** - `name`, `stream_id`, `epg_channel_id`, `stream_icon`
- **vod** - `name`, `stream_id`, `stream_icon`, `rating`, `container_extension`
- **series** - `name`, `stream_id`, `cover`, `rating`, `last_modified`
