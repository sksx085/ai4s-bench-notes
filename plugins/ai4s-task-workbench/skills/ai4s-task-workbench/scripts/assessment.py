"""Frozen participant bundles and independent rubric review of text submissions."""

import shutil
from contextlib import contextmanager

from audit import audit, public_assets
from contract import (
    ContractError, array, choice, digest, file_digest, identifier, json_bytes, local_file,
    obj, public_brief, read_json, rubric_levels, text, validate_csv, validate_output,
)


@contextmanager
def new_directory(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir()
    try:
        yield path
    except BaseException:
        shutil.rmtree(path)
        raise


def freeze(spec, root, destination, additions=()):
    report = audit(spec, root, additions)
    if not report["solver_snapshot_ready"]:
        pending = [i["message"] for i in report["findings"] if i["area"] == "contract" and i["level"] == "pending"]
        raise ContractError("选手材料尚未齐全。\n" + "\n".join(pending))
    files = public_assets(spec, root)
    manifest = {
        "schema_version": 1,
        "task_id": spec["task_id"],
        "revision": spec["revision"],
        "network": spec["constraints"]["network"],
        "submission": spec["submission"],
        "files": report["public_sha256"],
    }
    manifest["sha256"] = digest(json_bytes(manifest))
    with new_directory(destination) as dest:
        player = dest / "participant"
        player.mkdir()
        for name, file in files.items():
            target = player / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, target)
        if "challenge.md" not in files:
            (player / "challenge.md").write_bytes(public_brief(spec, root, additions).encode())
        verify_files(player, manifest["files"])
        (dest / "snapshot.json").write_bytes(json_bytes(manifest))
    return manifest


def verify_files(directory, files):
    if directory.is_symlink():
        raise ContractError("快照的 participant 目录不可为符号链接")
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file() or p.is_symlink()}
    if actual != set(files):
        raise ContractError(f"快照文件与清单不符。缺 {len(set(files) - actual)} 个，多 {len(actual - set(files))} 个")
    for name, expected in files.items():
        if file_digest(local_file(directory, name)) != expected:
            raise ContractError(f"快照内文件有变化：{name}")


def load_snapshot(path):
    manifest = obj(read_json(path / "snapshot.json"), "快照")
    verify_fingerprint(manifest, "快照")
    verify_files(path / "participant", obj(manifest.get("files"), "快照文件"))
    return manifest


def validate_submission(outputs, source_files, answer_dir):
    if not answer_dir.is_dir():
        raise ContractError(f"答卷目录不存在：{answer_dir}")
    if not outputs:
        raise ContractError("题目尚未定义提交格式")
    validated = {}
    for output in outputs:
        validate_output(output)
        name = output["path"]
        if not output["required"] and not (answer_dir / name).exists():
            continue
        path = local_file(answer_dir, name)
        if output["format"] == "csv":
            cases = output.get("keys_from")
            if cases and cases not in source_files:
                raise ContractError(f"找不到公开键表：{cases}")
            validated[name] = {"rows": validate_csv(output, path, source_files.get(cases))}
        else:
            if output["format"] == "json":
                read_json(path)
            with path.open("rb") as stream:
                if not stream.read(1):
                    raise ContractError(f"文件为空：{name}")
            validated[name] = {"bytes": path.stat().st_size}
    return validated


def judge_packet(spec, root, answer_paths, additions=()):
    criteria = [c for c in spec["assessment"]["criteria"] if c["method"] == "rubric"]
    if not criteria:
        raise ContractError("题目没有使用评分细则的评阅项")
    # An adjudicator sees only the selected text and public instructions. The caller chooses what to redact.
    answers = [
        {"id": f"s{index:03d}", "text": text(path.read_text(encoding="utf-8"), "评阅文本")}
        for index, path in enumerate(answer_paths, 1)
    ]
    contents = {
        "schema_version": 1, "task_id": spec["task_id"], "revision": spec["revision"],
        "brief": public_brief(spec, root, additions), "criteria": criteria, "answers": answers,
    }
    contents["sha256"] = digest(json_bytes(contents))
    return contents


def verify_fingerprint(contents, label):
    claimed = contents.get("sha256")
    if contents.get("schema_version") != 1 or claimed != digest(json_bytes({k: v for k, v in contents.items() if k != "sha256"})):
        raise ContractError(f"{label}摘要或版本不一致")


def load_packet(path):
    packet = obj(read_json(path), "盲评包")
    verify_fingerprint(packet, "盲评包")
    answers, criteria = {}, {}
    for answer in array(packet.get("answers"), "盲评答卷"):
        obj(answer, "盲评答卷")
        key = identifier(answer.get("id"), "答卷 ID")
        if key in answers:
            raise ContractError(f"题卷 {key} 重复")
        answers[key] = text(answer.get("text"), key)
    for criterion in array(packet.get("criteria"), "盲评判据"):
        obj(criterion, "盲评判据")
        key = identifier(criterion.get("id"), "评分项 ID")
        if key in criteria or criterion.get("method") != "rubric":
            raise ContractError(f"盲评项 {key} 重复或模式不符")
        criteria[key] = rubric_levels(criterion, key)
    if not answers or not criteria:
        raise ContractError("盲评包须同时包含作答和评分判据")
    return packet, answers, criteria


def review_template(path, reviewer_id, kind):
    packet, answers, criteria = load_packet(path)
    return {
        "packet_sha256": packet["sha256"], "reviewer_id": identifier(reviewer_id, "评审 ID"), "reviewer_kind": kind,
        "ratings": [
            {"answer": a, "criterion": c, "level": "", "quote": None, "reason": ""}
            for a in answers for c in criteria
        ],
    }


def load_ratings(path, packet, answers, criteria):
    review = obj(read_json(path), "评审记录")
    if review.get("packet_sha256") != packet["sha256"]:
        raise ContractError(f"{path.name} 的盲评包摘要不一致")
    reviewer = identifier(review.get("reviewer_id"), "评审 ID")
    kind = choice(review.get("reviewer_kind"), ("human", "model"), "评审类型")
    ratings = {}
    expected = {(a, c) for a in answers for c in criteria}
    for row in array(review.get("ratings"), "评审项"):
        obj(row, "评审项")
        a, c = text(row.get("answer"), "答卷 ID"), text(row.get("criterion"), "评分项 ID")
        if (a, c) not in expected or (a, c) in ratings:
            raise ContractError(f"{path.name} 中的评审项 {a}/{c} 重复或无效")
        choice(row.get("level"), criteria[c], f"{a}/{c}.level")
        text(row.get("reason"), f"{a}/{c}.reason")
        if row.get("quote") is not None and text(row["quote"], f"{a}/{c}.quote") not in answers[a]:
            raise ContractError(f"{path.name} 的 {a}/{c} 引文未出现在答卷")
        ratings[a, c] = row
    if len(ratings) != len(expected):
        raise ContractError(f"{path.name} 缺 {len(expected) - len(ratings)} 个评审项")
    return {"id": reviewer, "kind": kind}, ratings


def reconcile(packet_path, first, second):
    packet, answers, criteria = load_packet(packet_path)
    a, left = load_ratings(first, packet, answers, criteria)
    b, right = load_ratings(second, packet, answers, criteria)
    if a["id"] == b["id"]:
        raise ContractError("两次独立评阅需要不同的评审 ID")
    disagreements = []
    totals = {criterion: {"agree": 0, "total": len(answers)} for criterion in criteria}
    for key, rating in left.items():
        answer, criterion = key
        other = right[key]
        if rating["level"] == other["level"]:
            totals[criterion]["agree"] += 1
        else:
            disagreements.append({"answer": answer, "criterion": criterion, "ratings": {a["id"]: rating, b["id"]: other}})
    return {
        "packet_sha256": packet["sha256"], "reviewers": [a, b], "by_criterion": totals,
        "agree": len(left) - len(disagreements), "total": len(left), "disagreements": disagreements,
    }
