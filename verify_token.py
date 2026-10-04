"""
verify_token.py - Backward Compatibility Wrapper
Delegates to postpilot_cli.py verify-token command.
"""
import sys
import postpilot_cli

def main():
    return postpilot_cli.cmd_verify_token()

if __name__ == "__main__":
    sys.exit(main() or 0)