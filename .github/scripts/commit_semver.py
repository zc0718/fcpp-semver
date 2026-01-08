import json
import subprocess
import sys
import re
from pathlib import Path
from datetime import date


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def analyze_commits():
    # 1. 寻找上一个 release 的 hash
    # 注意：确保 grep 的字符串和你 commit_msg 的前缀完全一致
    result = run("git log --grep='chore(release):' -n 1 --format=%H")
    since = result.stdout.strip()
    
    # 2. 构建 git log 命令
    # %s 是主题，%b 是正文，%h 是简短 hash
    # 我们用一个极罕见的字符组合作为 commit 间的分隔符
    format_str = "%s%n%b---ENDMSG---%h"
    if since:
        cmd = f"git log {since}..HEAD --format='{format_str}'"
    else:
        cmd = f"git log --format='{format_str}'"

    result = run(cmd)
    if not result.stdout.strip():
        return 0, {}

    # 3. 解析
    # 先按 commit 分隔
    raw_blocks = result.stdout.strip().split("---ENDMSG---")
    
    level = 0
    entries = {
        "Breaking Changes": [],
        "Features": [],
        "Bug Fixes": [],
        "Performance Improvements": [],
        "Others": []
    }

    # raw_blocks 的结构现在是: [msg1, hash1\nmsg2, hash2...] 
    # 需要精细化处理偏移
    for i in range(len(raw_blocks) - 1):
        # 当前块包含 msg
        full_msg = raw_blocks[i].strip()
        # 下一个块的开头包含当前 commit 的 hash
        current_hash = raw_blocks[i+1].splitlines()[0].strip()
        
        if not full_msg or "[skip ci]" in full_msg:
            continue

        first_line = full_msg.splitlines()[0]
        
        current_msg_level = 0
        category = "Others"

        # 判定
        if "BREAKING CHANGE" in full_msg or re.match(r"^[a-z]+(\([^)]*\))?!:", first_line):
            current_msg_level = 3
            category = "Breaking Changes"
        elif re.match(r"^feat(\([^)]*\))?:", first_line):
            current_msg_level = 2
            category = "Features"
        elif re.match(r"^(fix|perf)(\([^)]*\))?:", first_line):
            current_msg_level = 1
            category = "Bug Fixes" if "fix" in first_line else "Performance Improvements"

        level = max(level, current_msg_level)
        # 只在有意义的分类下添加，或者你想保留 Others
        entry = f"- {first_line} ({current_hash})"
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

