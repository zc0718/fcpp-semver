import json
import subprocess
import sys
import re
from pathlib import Path
from datetime import date


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def analyze_commits():
    result = run("git log --oneline --grep='chore(release):' -n 1 --pretty=format:%H")
    since = ''
    if result.stdout.strip():
        since = result.stdout.strip()
        cmd = f"git log {since}..HEAD --pretty=format:'%s---DELIMITER---%h'"
    else:
        cmd = "git log --all --pretty=format:'%s---DELIMITER---%h'"

    result = run(cmd)
    if result.returncode != 0:
        return 0, {}

    raw_commits = result.stdout.strip().split("---DELIMITER---")
    
    level = 0
    entries = {
        "Breaking Changes": [],
        "Features": [],
        "Bug Fixes": [],
        "Performance Improvements": [],
        "Others": []
    }

    for i in range(0, len(raw_commits), 2):
        if i+1 >= len(raw_commits): break
        msg = raw_commits[i].strip()
        hash_ = raw_commits[i+1].strip()

        if not msg or "[skip ci]" in msg:
            if level > 0: break
            continue

        lines = msg.splitlines()
        first_line = lines[0]

        current_msg_level = 0
        category = "Others"

        if "BREAKING CHANGE" in msg or re.match(r"^[a-z]+(\([^)]*\))?!:", first_line):
            current_msg_level = 3
            category = "Breaking Changes"
        elif re.match(r"^feat(\([^)]*\))?:", first_line):
            current_msg_level = 2
            category = "Features"
        elif re.match(r"^(fix|perf)(\([^)]*\))?:", first_line):
            current_msg_level = 1
            category = "Bug Fixes" if "fix" in first_line else "Performance Improvements"

        level = max(level, current_msg_level)
        entry = f"- {first_line} ({hash_})"
        entries[category].append(entry)

    return level, entries


def main():
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent.parent
    metadata_path = root_dir / "metadata.json"
    changelog_path = root_dir / "CHANGELOG.md"

    if not metadata_path.exists():
        print(f"Error: {metadata_path} not found")
        sys.exit(1)

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    v_curr = metadata["version"]
    major, minor, patch = map(int, v_curr.split("."))

    bump_level, log_entries = analyze_commits()

    if bump_level == 0:
        print("No relevant changes detected. Skipping release.")
        sys.exit(0)

    if bump_level == 3:
        new_version = f"{major + 1}.0.0"
    elif bump_level == 2:
        new_version = f"{major}.{minor + 1}.0"
    else:
        new_version = f"{major}.{minor}.{patch + 1}"

    print(f"Bumping {v_curr} -> {new_version} (Level {bump_level})")

    metadata["version"] = new_version
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
        f.write("\n")

    if log_entries:
        new_log = f"## [{new_version}] - {date.today().isoformat()}\n\n"
        for category, items in log_entries.items():
            if items:
                new_log += f"**{category}**\n"
                new_log += "\n".join(items) + "\n\n"
        
        content = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else ""
        changelog_path.write_text(new_log + content, encoding="utf-8")

    run("git config user.name 'github-actions'")
    run("git config user.email 'github-actions@github.com'")
    run(f"git add {metadata_path} {changelog_path}")
    run(f'git commit -m "chore(release): {new_version} [skip ci]"')


if __name__ == "__main__":
    main()

