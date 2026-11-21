"""AI4S task workbench. Run with Python 3.9 or newer."""

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from assessment import freeze, judge_packet, load_snapshot, new_directory, reconcile, review_template, validate_submission
from audit import audit, public_assets
from contract import (
    ContractError, digest, file_digest, json_bytes, local_file, obj, public_brief,
    read_json, render, string_list, validate_spec,
)


def init(destination, task_id, title, existing_brief, material_root=None):
    if destination.is_symlink():
        raise ContractError("新建目录不可为符号链接")
    destination = destination.resolve()
    organizer_file = destination / "organizer/review.json"
    root = material_root.resolve() if material_root else (Path.cwd() if existing_brief else destination)
    try:
        review_reference = organizer_file.relative_to(root).as_posix()
    except ValueError as exc:
        raise ContractError("新建目录须位于材料根目录内。请用 --root 指定共同根目录") from exc
    if existing_brief:
        candidate = Path(existing_brief)
        if candidate.is_absolute():
            original_root = material_root.absolute() if material_root else root
            for base in (original_root, root):
                if candidate.is_relative_to(base):
                    existing_brief = candidate.relative_to(base).as_posix()
                    break
            else:
                raise ContractError("旧题面须位于材料根目录内。请用 --root 指定共同根目录")
        local_file(root, existing_brief)
    spec = {
        "schema_version": 1, "task_id": task_id, "title": title, "revision": "draft",
        "sections": {"goal": "", "input": "", "constraints": ""},
        "constraints": {"network": "undecided", "allowed": [], "forbidden": []},
        "public": {"brief": existing_brief, "files": {}},
        "submission": [],
        "assessment": {"criteria": [], "scorer": None},
        "review": review_reference,
    }
    review = {"reference_policy": "declared", "evidence": [], "target_evidence": [], "claims": [],
              "baselines": [], "checks": [], "private_files": []}
    validate_spec(spec)
    with new_directory(destination):
        (destination / "organizer").mkdir()
        organizer_file.write_bytes(json_bytes(review))
        (destination / "challenge.json").write_bytes(json_bytes(spec))
        if not existing_brief:
            (destination / "participant").mkdir()
            (destination / "participant/challenge.md").write_text(render(spec), encoding="utf-8")
    return {"spec": str(destination / "challenge.json"), "review": str(organizer_file), "root": str(root)}


def load_spec(path, root):
    spec = read_json(path)
    validate_spec(spec)
    return spec, root.resolve() if root else path.resolve().parent


def replay(spec, root, answer_dir, timeout_s):
    assessment = spec["assessment"]
    if not assessment.get("scorer"):
        raise ContractError("题目尚未接入本地 Python 评分器")
    scorer = local_file(root, assessment["scorer"])
    if scorer.suffix != ".py" or timeout_s <= 0:
        raise ContractError("需要已审阅的 Python 评分器和正数超时")
    files = public_assets(spec, root)
    format_result = validate_submission(spec["submission"], files, answer_dir)
    substitutions = [s.replace("{submission}", str(answer_dir)) for s in assessment["score_args"]]
    review_path = local_file(root, spec["review"])
    review = obj(read_json(review_path), "组织方记录")
    private = string_list(review.get("private_files"), "private_files")
    additions = [local_file(root, name) for name in (*private, *assessment.get("score_dependencies", []))]
    data_paths = {str(path.relative_to(root)): path for path in [review_path, *files.values(), *additions]}
    answer_paths = {name: local_file(answer_dir, name) for name in format_result}
    data_hashes = {name: file_digest(path) for name, path in data_paths.items()}
    answer_hashes = {name: file_digest(path) for name, path in answer_paths.items()}
    grader_hash = file_digest(scorer)
    child_env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ") if key in os.environ}
    child_env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, "-B", str(scorer), *substitutions],
        cwd=scorer.parent, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        encoding="utf-8", timeout=timeout_s, check=False, env=child_env,
    )
    if result.returncode != 0:
        raise ContractError(f"评分器运行失败（退出码 {result.returncode}）：{result.stderr.strip()[-700:]}")
    if grader_hash != file_digest(scorer):
        raise ContractError("评分器在运行期间发生变化")
    for paths, hashes in ((data_paths, data_hashes), (answer_paths, answer_hashes)):
        if any(file_digest(path) != hashes[name] for name, path in paths.items()):
            raise ContractError("评分期间有已登记的数据或答卷发生变化")
    grades = obj(json.loads(result.stdout), "评分器输出")
    if not grades:
        raise ContractError("评分器须输出非空 JSON 对象")
    return {
        "task_id": spec["task_id"], "revision": spec["revision"],
        "contract_sha256": digest(json_bytes(spec)), "scorer_sha256": grader_hash,
        "data_sha256": data_hashes,
        "submission_sha256": answer_hashes,
        "format": format_result, "grades": grades,
    }


def parser():
    main = argparse.ArgumentParser(description=__doc__)
    commands = main.add_subparsers(dest="command", required=True)
    scaffold = commands.add_parser("init", help="创建题目与组织方记录的最小骨架")
    scaffold.add_argument("directory", type=Path)
    scaffold.add_argument("--id", required=True)
    scaffold.add_argument("--title", required=True)
    scaffold.add_argument("--legacy-brief")
    scaffold.add_argument("--root", type=Path, help="新目录与现有题面的共同材料根目录")
    for name, help_text in {
        "brief": "输出选手看到的精简题面",
        "audit": "核查任务契约、公开输入、科学证据和评分边界",
        "freeze": "复制选手可见材料，并记录文件摘要",
        "replay": "显式执行已审阅的本地评分器，接收 JSON 结果",
        "judge-packet": "为提供的文本答卷生成同版本盲评包",
    }.items():
        command = commands.add_parser(name, help=help_text)
        command.add_argument("spec", type=Path)
        command.add_argument("--root", type=Path, help="相对材料路径的根目录。默认是规格所在目录")
        if name != "replay":
            command.add_argument("--add", action="append", default=[], choices=("background", "diagnostics"),
                                 help="按需加回背景或诊断评分。可重复")
        if name == "freeze":
            command.add_argument("destination", type=Path)
        elif name == "replay":
            command.add_argument("answers", type=Path)
            command.add_argument("--timeout", type=int, default=60)
        elif name == "judge-packet":
            command.add_argument("answers", type=Path, nargs="+")
    check = commands.add_parser("check-submission", help="校验文件、字段、值域与键覆盖")
    check.add_argument("answers", type=Path)
    source = check.add_mutually_exclusive_group(required=True)
    source.add_argument("--spec", type=Path)
    source.add_argument("--snapshot", type=Path)
    check.add_argument("--root", type=Path)
    template = commands.add_parser("judge-template", help="生成与盲评包绑定的独立评阅表")
    template.add_argument("packet", type=Path)
    template.add_argument("--id", required=True)
    template.add_argument("--kind", choices=("human", "model"), required=True)
    compare = commands.add_parser("reconcile", help="核对两份评阅的完整性、依据和分歧")
    for role in ("packet", "first", "second"):
        compare.add_argument(role, type=Path)
    return main


def run(args):
    command = args.command
    if command == "init":
        return init(args.directory, args.id, args.title, args.legacy_brief, args.root)
    if command == "judge-template":
        return review_template(args.packet, args.id, args.kind)
    if command == "reconcile":
        return reconcile(args.packet, args.first, args.second)
    if command == "check-submission" and args.snapshot:
        if args.root:
            raise ContractError("使用快照时，公开材料从其 participant 目录读取")
        manifest = load_snapshot(args.snapshot)
        files = {key: local_file(args.snapshot / "participant", key) for key in manifest["files"]}
        return {"snapshot_sha256": manifest["sha256"],
                "validated": validate_submission(manifest["submission"], files, args.answers)}
    spec, root = load_spec(args.spec, args.root)
    if command == "brief":
        return public_brief(spec, root, args.add)
    if command == "audit":
        return audit(spec, root, args.add)
    if command == "freeze":
        return freeze(spec, root, args.destination.absolute(), args.add)
    if command == "judge-packet":
        return judge_packet(spec, root, args.answers, args.add)
    if command == "replay":
        return replay(spec, root, args.answers.resolve(), args.timeout)
    return {"validated": validate_submission(spec["submission"], public_assets(spec, root), args.answers)}


def main():
    try:
        result = run(parser().parse_args())
        sys.stdout.write(result if isinstance(result, str) else json_bytes(result).decode())
    except (OSError, ValueError, csv.Error, subprocess.TimeoutExpired) as error:
        print(f"检查未完成。{error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
