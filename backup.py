"""
PostPilot Portable Data Export & Import Utility
Provides safe, portable transfer of PostPilot content across:
- Environment A: Web Server (Linux VPS)
- Environment B: Android Phone (Termux)
- Development Workstation (Windows / macOS)

Package Structure:
  postpilot-backup-[timestamp].zip
    ├── manifest.json   (metadata, counts, version, source environment)
    ├── posts.json      (post records using logical media filenames)
    ├── settings.json   (safe non-secret settings like task intervals)
    └── media/          (referenced images/videos)

Security Note:
  Passwords, user hashes, API tokens, secret keys, and .env files are
  NEVER included in exports. Credentials must be configured independently
  in the target environment.
"""
import os
import sys
import json
import zipfile
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

import config
import database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] (Backup) %(message)s")
logger = logging.getLogger(__name__)

BACKUP_VERSION = "1.0"

def export_backup(output_path=None):
    """
    Exports all posts, safe settings, and referenced media into a portable zip archive.
    Returns the Path to the generated zip file.
    """
    database.init_db()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if not output_path:
        output_dir = Path(config.DATA_DIR) / "backups"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"postpilot_backup_{timestamp}.zip"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Fetch posts across all types
    posts = []
    with database.get_db_connection() as conn:
        rows = conn.execute(
            "SELECT id, post_type, message, image_filename, created_at, last_posted_at "
            "FROM posts ORDER BY post_type, id ASC"
        ).fetchall()
        for r in rows:
            posts.append({
                'id': r['id'],
                'post_type': r['post_type'],
                'message': r['message'] or '',
                'image_filename': r['image_filename'] or '',
                'created_at': str(r['created_at']) if r['created_at'] else None,
                'last_posted_at': str(r['last_posted_at']) if r['last_posted_at'] else None
            })

    # 2. Fetch safe settings (task intervals only, strictly NO secrets/passwords)
    task_states = database.get_all_task_states()
    safe_settings = {
        'intervals': {
            name: state.get('interval', 1800)
            for name, state in task_states.items()
        }
    }

    # 3. Identify and collect media files
    media_filenames = set()
    for p in posts:
        fn = p.get('image_filename')
        if fn and fn.strip():
            # Use base filename to guarantee portability
            media_filenames.add(os.path.basename(fn.strip()))

    upload_folder = Path(config.UPLOAD_FOLDER)
    found_media = []
    missing_media = []

    for fn in media_filenames:
        src_path = upload_folder / fn
        if src_path.exists() and src_path.is_file():
            found_media.append(fn)
        else:
            missing_media.append(fn)

    # 4. Create manifest
    manifest = {
        'version': BACKUP_VERSION,
        'app': 'PostPilot',
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'source_env': config.APP_ENV,
        'total_posts': len(posts),
        'total_media_found': len(found_media),
        'total_media_missing': len(missing_media),
        'missing_media_list': missing_media
    }

    # 5. Build zip archive
    with zipfile.ZipFile(str(output_path), 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('manifest.json', json.dumps(manifest, indent=2))
        zf.writestr('posts.json', json.dumps(posts, indent=2))
        zf.writestr('settings.json', json.dumps(safe_settings, indent=2))

        for fn in found_media:
            src_file = upload_folder / fn
            zf.write(str(src_file), arcname=f"media/{fn}")

    logger.info(f"✅ Export completed successfully: {output_path}")
    logger.info(f"   Posts: {len(posts)}, Media: {len(found_media)}, Missing media: {len(missing_media)}")
    return output_path

def import_backup(zip_path, overwrite=False, import_settings=True):
    """
    Imports posts, safe settings, and media from a portable zip archive.
    Guarantees safe extraction against path traversal.
    """
    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise FileNotFoundError(f"Backup file not found: {zip_path}")

    database.init_db()
    upload_folder = Path(config.UPLOAD_FOLDER)
    upload_folder.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(zip_path), 'r') as zf:
        namelist = zf.namelist()

        if 'manifest.json' not in namelist or 'posts.json' not in namelist:
            raise ValueError("Invalid PostPilot backup: missing manifest.json or posts.json")

        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
        posts_data = json.loads(zf.read('posts.json').decode('utf-8'))
        
        settings_data = {}
        if 'settings.json' in namelist:
            try:
                settings_data = json.loads(zf.read('settings.json').decode('utf-8'))
            except Exception as e:
                logger.warning(f"Could not parse settings.json: {e}")

        # 1. Extract media files safely
        media_extracted = 0
        for entry in namelist:
            if entry.startswith('media/') and len(entry) > len('media/'):
                safe_name = os.path.basename(entry)
                if not safe_name:
                    continue
                dest_file = upload_folder / safe_name
                if not dest_file.exists() or overwrite:
                    with zf.open(entry) as src, open(dest_file, 'wb') as dst:
                        dst.write(src.read())
                    media_extracted += 1

        # 2. Import posts into database
        if overwrite:
            for p_type in ('tour', 'nz', 'gaatha', 'insta'):
                database.delete_all_posts_by_type(p_type)
            logger.info("Cleared existing posts (--overwrite active)")

        imported_count = 0
        skipped_count = 0

        for post in posts_data:
            p_type = post.get('post_type')
            msg = post.get('message', '')
            raw_img = post.get('image_filename', '')
            img_fn = os.path.basename(raw_img) if raw_img else ''

            if not p_type or p_type not in {'tour', 'nz', 'gaatha', 'insta'}:
                skipped_count += 1
                continue

            # Check for duplicate if not overwriting
            if not overwrite:
                with database.get_db_connection() as conn:
                    existing = conn.execute(
                        "SELECT id FROM posts WHERE post_type = ? AND message = ? AND image_filename = ?",
                        (p_type, msg, img_fn)
                    ).fetchone()
                    if existing:
                        skipped_count += 1
                        continue

            database.add_post(p_type, msg, img_fn)
            imported_count += 1

        # 3. Apply safe settings if requested
        if import_settings and 'intervals' in settings_data:
            for task_name, interval in settings_data['intervals'].items():
                if task_name in {'tour', 'nz', 'gaatha', 'insta'} and isinstance(interval, int) and interval > 0:
                    database.set_task_state(task_name, interval_seconds=interval)
                    logger.info(f"Updated interval for {task_name} -> {interval}s")

    result = {
        'status': 'success',
        'source_env': manifest.get('source_env', 'unknown'),
        'exported_at': manifest.get('exported_at'),
        'posts_imported': imported_count,
        'posts_skipped': skipped_count,
        'media_extracted': media_extracted,
        'target_upload_folder': str(upload_folder)
    }
    logger.info(f"✅ Import completed: {imported_count} posts imported, {skipped_count} skipped, {media_extracted} media extracted")
    return result

def main():
    parser = argparse.ArgumentParser(description="PostPilot Portable Data Export & Import CLI")
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export posts, safe settings, and media to zip")
    export_parser.add_argument("--output", "-o", help="Output zip file path (default: data/backups/postpilot_backup_[timestamp].zip)")

    # Import command
    import_parser = subparsers.add_parser("import", help="Import posts, safe settings, and media from zip")
    import_parser.add_argument("--input", "-i", required=True, help="Path to PostPilot backup zip file")
    import_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing posts and media")
    import_parser.add_argument("--no-settings", action="store_true", help="Do not import task intervals from backup")

    args = parser.parse_args()

    if args.action == "export":
        out = export_backup(args.output)
        print(f"\n[PostPilot] Backup exported to: {out}\n")
    elif args.action == "import":
        res = import_backup(args.input, overwrite=args.overwrite, import_settings=not args.no_settings)
        print(f"\n[PostPilot] Backup imported successfully:\n{json.dumps(res, indent=2)}\n")
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
