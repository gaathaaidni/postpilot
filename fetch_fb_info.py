"""
fetch_fb_info.py - Backward Compatibility Wrapper
Delegates to postpilot_cli.py list-pages --update-env command.
"""
import sys
import postpilot_cli

def main():
    return postpilot_cli.cmd_list_pages(update_env=True)

if __name__ == "__main__":
    sys.exit(main() or 0)
