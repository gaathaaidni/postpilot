# PostPilot — Portable Data Export & Import Specification

This document defines the specification, format, and operations for exporting and importing PostPilot content seamlessly across Windows development, Android Termux, and Linux Web Server environments.

---

## 1. Migration Architecture

The export/import system enables seamless bidirectional portability:

```text
       Phone / Termux
             │ (python backup.py export)
             ▼
   Portable PostPilot Backup (.zip)
             │ (python backup.py import)
             ▼
      Linux Web Server
```

And in reverse:

```text
      Linux Web Server
             │ (python backup.py export)
             ▼
   Portable PostPilot Backup (.zip)
             │ (python backup.py import)
             ▼
       Phone / Termux
```

---

## 2. Archive Specification

A PostPilot backup is a standard ZIP archive compressed with DEFLATE containing:

```text
postpilot_backup_YYYYMMDD_HHMMSS.zip
├── manifest.json    # Metadata, version, export timestamp, environment, counts
├── posts.json       # All post records with logical media filenames
├── settings.json    # Safe application settings (task intervals only)
└── media/           # Referenced images and videos
    ├── post_1710000001_a1b2.png
    └── post_1710000002_c3d4.jpg
```

### A. `manifest.json`
Provides environment metadata and integrity verification:

```json
{
  "version": "1.0",
  "app": "PostPilot",
  "exported_at": "2026-10-03T03:30:00Z",
  "source_env": "termux",
  "total_posts": 42,
  "total_media_found": 39,
  "total_media_missing": 0,
  "missing_media_list": []
}
```

### B. `posts.json`
Stores posts across all modules (`tour`, `nz`, `gaatha`, `insta`). Media is referenced exclusively by **logical filename**, never by operating system absolute paths:

```json
[
  {
    "id": 1,
    "post_type": "tour",
    "message": "Discover our luxury holiday packages in Dubai!",
    "image_filename": "post_1710000001_a1b2.png",
    "created_at": "2026-10-01 12:00:00",
    "last_posted_at": "2026-10-02 18:30:00"
  }
]
```

### C. `settings.json`
Stores safe, non-sensitive module posting intervals:

```json
{
  "intervals": {
    "tour": 1800,
    "nz": 1800,
    "gaatha": 1800,
    "insta": 180
  }
}
```

---

## 3. Strict Security Boundaries

> [!CAUTION]
> Credentials, tokens, and secrets are **strictly excluded** from all export packages:
> - **Plaintext passwords**: NEVER exported
> - **Password hashes / user accounts**: NEVER exported
> - **Flask secret keys**: NEVER exported
> - **Meta/Facebook OAuth access tokens**: NEVER exported
> - **Environment files (`.env`)**: NEVER exported
> - **Database connection strings**: NEVER exported
> 
> When importing content into a new environment (e.g. from Termux to Production Server), administrative credentials and API tokens must be configured independently in the target environment's `.env` file.

### Path Traversal Defense (Zip-Slip Prevention)
When extracting the `media/` directory during import, `backup.py` enforces `os.path.basename(entry)` on every member, ensuring that crafted archives containing directory traversal payloads (e.g., `../../etc/cron.d/evil`) cannot escape the target `config.UPLOAD_FOLDER`.

---

## 4. Media Portability Across Platforms

| Platform | Filesystem Root | Media Storage Path | Logical Reference in Backup |
| :--- | :--- | :--- | :--- |
| **Windows Dev** | `C:\Users\...\postpilot` | `data\images\post_123.jpg` | `post_123.jpg` |
| **Android Termux** | `/data/data/com.termux/files/home/postpilot` | `data/images/post_123.jpg` | `post_123.jpg` |
| **Linux Server** | `/opt/postpilot` | `/opt/postpilot/data/images/post_123.jpg` | `post_123.jpg` |

Because only the filename (`post_123.jpg`) is recorded in the backup:
1. Exporting on Windows packages `data\images\post_123.jpg` into `media/post_123.jpg`.
2. Importing on Linux Server unpacks `media/post_123.jpg` into `/opt/postpilot/data/images/post_123.jpg`.
3. Posts link seamlessly without any broken image paths.

---

## 5. CLI Usage

### Exporting Content
Export all posts and media into the default `data/backups/` directory:
```bash
python backup.py export
```

Specify a custom export destination:
```bash
python backup.py export --output /tmp/my_postpilot_export.zip
```

### Importing Content
Import from a backup zip archive (skips duplicates by default):
```bash
python backup.py import --input /path/to/postpilot_backup.zip
```

Overwrite existing posts and replace matching media files:
```bash
python backup.py import --input /path/to/postpilot_backup.zip --overwrite
```

Import posts and media while preserving current task intervals:
```bash
python backup.py import --input /path/to/postpilot_backup.zip --no-settings
```

---

## 6. Programmatic Python API

```python
import backup

# Export
backup_zip = backup.export_backup(output_path="custom_backup.zip")
print(f"Exported to: {backup_zip}")

# Import
result = backup.import_backup(
    zip_path="custom_backup.zip",
    overwrite=False,
    import_settings=True
)
print(f"Imported {result['posts_imported']} posts, extracted {result['media_extracted']} media files.")
```

---

## 7. SQLite Hot Backup vs Portable Archive

| Feature | `database.backup_sqlite_db()` | `backup.py export` |
| :--- | :--- | :--- |
| **Scope** | Complete low-level SQLite database file | Posts, safe settings, and media files |
| **Destination** | Raw `.db` file | Portable `.zip` archive |
| **Format** | SQLite-only binary | Portable JSON + Media |
| **Cross-Platform** | Only between identical SQLite architectures | Universal (Windows, Termux, Linux, Postgres) |
| **Includes Passwords** | Yes (preserves user hashes for server restore) | **No** (excludes credentials for safe transit) |
| **Primary Use** | Local disaster recovery and rollback | Cross-environment migration and sharing |
