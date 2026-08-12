import sys
import json
import re

def main():
    try:
        # Read from stdin
        input_data = sys.stdin.read()
        if not input_data:
            # If no input, default to allow
            print(json.dumps({
                "decision": "allow",
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow"
                }
            }))
            return

        payload = json.loads(input_data)
        # Extract the tool name and arguments
        tool_name = payload.get("tool_name", "")
        args = payload.get("toolCall", {}).get("args", {})
        command_line = args.get("CommandLine", "")

        # Check if we are destroying postgres
        if "dropdb" in command_line.lower() or "drop database" in command_line.lower():
            delete_keywords = ["dropdb", "drop", "delete"]
            is_delete = False
            for kw in delete_keywords:
                # Match the keyword as a whole word
                if re.search(r'\b' + re.escape(kw) + r'\b', command_line.lower()):
                    is_delete = True
                    break
            
            if is_delete:
                # Deny tool execution
                print(json.dumps({
                    "decision": "deny",
                    "reason": "BLOCKED: You cannot delete the database file!",
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "BLOCKED: You cannot delete the database file!"
                    }
                }))
                sys.exit(2)

        # Allow by default
        print(json.dumps({
            "decision": "allow",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow"
            }
        }))
    except Exception as e:
        sys.stderr.write(f"Hook error: {str(e)}\n")
        # Default to allow on unexpected error to avoid blocking developer workflow
        print(json.dumps({
            "decision": "allow",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow"
            }
        }))

if __name__ == "__main__":
    main()
