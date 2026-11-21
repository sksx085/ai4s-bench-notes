"""Check public materials, evidence links, and assessment declarations."""

import re

from contract import (
    CORE_HEADINGS, ContractError, SECTIONS, array, choice, digest, expected_keys, file_digest, identifier,
    local_file, number, obj, public_brief, read_json, string_list, text, uses_scoring, validate_spec,
)


def public_assets(spec, root):
    files = {name: local_file(root, source) for name, source in spec["public"]["files"].items()}
    if source := spec["public"].get("brief"):
        files["challenge.md"] = local_file(root, source)
    return files


def load_review(spec, root):
    review = obj(read_json(local_file(root, spec["review"])), "组织方记录")
    policy = choice(review.get("reference_policy"), ("declared", "measured-only"), "reference_policy")
    evidence = {}
    paths = {}
    for item in array(review.get("evidence"), "evidence"):
        obj(item, "证据条目")
        key = identifier(item.get("id"), "evidence.id")
        if key in evidence:
            raise ContractError(f"证据 ID 重复：{key}")
        kind = choice(item.get("kind"), ("measured", "derived", "simulation", "document"), f"{key}.kind")
        text(item.get("locator"), f"{key}.locator")
        paths[key] = local_file(root, item.get("path"))
        parents = string_list(item.get("parents", []), f"{key}.parents")
        if (kind == "derived") != bool(parents) or len(set(parents)) != len(parents):
            raise ContractError(f"{key} 的实测派生链应有独立的上游证据 ID")
        evidence[key] = {**item, "parents": parents}

    def check_refs(keys, where):
        keys = string_list(keys, where)
        if len(set(keys)) != len(keys) or set(keys) - evidence.keys():
            raise ContractError(f"{where} 含重复或未知的证据 ID")
        return keys

    ancestry = {}

    def trace(key, parents):
        if key in parents:
            raise ContractError(f"循环证据链：{' → '.join((*parents, key))}")
        if key not in ancestry:
            item = evidence[key]
            inputs = check_refs(item["parents"], f"{key}.parents")
            ancestry[key] = set().union(*(trace(i, (*parents, key)) for i in inputs)) if inputs else {item["kind"]}
        return ancestry[key]

    for key in evidence:
        trace(key, ())
    targets = check_refs(review.get("target_evidence"), "target_evidence")
    if policy == "measured-only":
        for key in targets:
            if ancestry[key] != {"measured"}:
                raise ContractError(f"实测限定题的参考值 {key} 必须最终来自测量记录")
    claims = {}
    for item in array(review.get("claims"), "claims"):
        obj(item, "科学主张")
        key = identifier(item.get("id"), "claims.id")
        if key in claims:
            raise ContractError(f"科学主张 ID 重复：{key}")
        text(item.get("claim"), f"{key}.claim")
        text(item.get("reason"), f"{key}.reason")
        verdict = choice(item.get("verdict"), ("supported", "limited", "open", "refuted"), f"{key}.verdict")
        refs = check_refs(item.get("evidence"), f"{key}.evidence")
        if verdict != "open" and not refs:
            raise ContractError(f"科学主张 {key} 的判断缺少证据")
        if verdict != "supported":
            text(item.get("next_check"), f"{key}.next_check")
        claims[key] = item
    rule_ids = {c["id"] for c in spec["assessment"]["criteria"] if c["method"] == "rule"}
    for baseline in array(review.get("baselines"), "baselines"):
        obj(baseline, "基线")
        text(baseline.get("name"), "baselines.name")
        text(baseline.get("method"), "baselines.method")
        number(baseline.get("value"), "baselines.value")
        if text(baseline.get("criterion"), "baselines.criterion") not in rule_ids:
            raise ContractError("基线须对应一个已定义的程序评分项")
        refs = check_refs(baseline.get("evidence"), "baselines.evidence")
        if not refs:
            raise ContractError("已有基线须关联实际运行记录")
        if record := baseline.get("value_from"):
            obj(record, "baselines.value_from")
            evidence_id = identifier(record.get("evidence"), "baselines.value_from.evidence")
            keys = string_list(record.get("keys"), "baselines.value_from.keys")
            if evidence_id not in refs or not keys:
                raise ContractError("核对基线数值须指定已关联的 JSON 证据和字段")
            current = read_json(paths[evidence_id])
            for key in keys:
                if not isinstance(current, dict) or key not in current:
                    raise ContractError(f"基线 {baseline['name']} 的记录缺少字段 {key}")
                current = current[key]
            if number(current, baseline["name"]) != baseline["value"]:
                raise ContractError(f"基线 {baseline['name']} 与实际运行记录数值不同")
    checks = array(review.get("checks"), "checks")
    for check in checks:
        obj(check, "核查记录")
        choice(check.get("area"), ("science", "scorer", "rubric", "isolation"), "checks.area")
        choice(check.get("result"), ("pass", "fail"), "checks.result")
        text(check.get("description"), "checks.description")
        if not check_refs(check.get("evidence"), "checks.evidence"):
            raise ContractError("已运行的核查须关联证据")
    private = [local_file(root, name) for name in string_list(review.get("private_files"), "private_files")]
    return review, evidence, paths, ancestry, list(claims.values()), private


def assessment_mode(criteria):
    methods = {item["method"] for item in criteria}
    return {frozenset(): "undecided", frozenset({"rule"}): "objective", frozenset({"rubric"}): "rubric",
            frozenset({"rule", "rubric"}): "mixed"}[frozenset(methods)]


def audit(spec, root, additions=()):
    criteria = validate_spec(spec)
    files = public_assets(spec, root)
    brief = public_brief(spec, root, additions)
    review, evidence, paths, ancestry, claims, private = load_review(spec, root)
    scorer = spec["assessment"].get("scorer")
    scored = uses_scoring(spec)
    excluded = [local_file(root, spec["review"]), *private]
    if scorer:
        excluded.append(local_file(root, scorer))
        for name in spec["assessment"].get("score_dependencies", []):
            local_file(root, name)
    blocked_hashes = {file_digest(path) for path in excluded}
    public_hashes = {name: file_digest(path) for name, path in files.items()}
    public_hashes.setdefault("challenge.md", digest(brief.encode()))
    leaks = sorted(name for name, sha in public_hashes.items() if sha in blocked_hashes)
    if leaks:
        raise ContractError(f"选手文件与声明的组织方文件内容相同：{'、'.join(leaks)}")

    findings = []
    brief_name = spec["public"].get("brief")
    if brief_name:
        headings = re.findall(r"^#{1,6}\s+([^\n]+)", brief, re.MULTILINE)
        missing_sections = [h for h in SECTIONS if not any(re.search(rf"\b{h}\b", title, re.I) for title in headings)]
        chinese_headings = set(CORE_HEADINGS) | ({"评分"} if scored else set())
        if missing_sections and not (chinese_headings.issubset(headings)
                                     or {"问题", "解答", "约束"}.issubset(headings)):
            findings.append({"area": "contract", "level": "review", "message": "请核对旧题面的目标、交付和限制是否齐全"})
    else:
        required = ["goal", *(["input"] if spec["public"]["files"] else [])]
        missing = [f"sections.{key}" for key in required if not spec["sections"].get(key, "").strip()]
        if missing:
            findings.append({"area": "contract", "level": "pending", "message": "待填写：" + "、".join(missing)})
    outputs = spec["submission"]
    if not any(item["required"] for item in outputs):
        findings.append({"area": "contract", "level": "pending", "message": "待确定必交文件"})
    for output in outputs:
        if brief_name and output["path"] not in brief:
            findings.append({"area": "contract", "level": "review", "message": f"旧题面未找到提交文件名 {output['path']}"})
        if cases := output.get("keys_from"):
            if not (output["format"] == "csv" and cases in files):
                raise ContractError(f"{output['path']} 的行键来源须列为选手 CSV 文件")
            expected_keys(output, files[cases])
    if spec["constraints"]["network"] == "undecided":
        findings.append({"area": "contract", "level": "pending", "message": "待确认选手联网规则"})
    primary = [c for c in criteria.values() if c["role"] == "primary"]
    if scored and not primary:
        findings.append({"area": "contract", "level": "pending", "message": "待确定主指标或主要评分规则"})
    if any(c["method"] == "rule" for c in criteria.values()) and not scorer:
        findings.append({"area": "assessment", "level": "pending", "message": "已定义程序评分项，待接入科学评分器"})
    if not review["target_evidence"]:
        findings.append({"area": "science", "level": "pending", "message": "待将评测对象关联到原始证据"})
    if not claims:
        findings.append({"area": "science", "level": "pending", "message": "待记录可检验的科学主张"})
    for claim in claims:
        if claim["verdict"] != "supported":
            findings.append({"area": "science", "level": claim["verdict"], "id": claim["id"],
                             "message": claim["reason"], "next_check": claim["next_check"]})
    if scored and not review["baselines"] and not any(c["method"] == "rubric" for c in primary):
        findings.append({"area": "science", "level": "pending", "message": "待记录基线或在审题中说明无需数值基线的依据"})
    for check in review["checks"]:
        if check["result"] == "fail":
            findings.append({"area": check["area"], "level": "fail", "message": check["description"]})
    for area, condition, message in [
        ("scorer", bool(scorer), "待记录原评分器的边界及错误输入检查"),
        ("rubric", any(c["method"] == "rubric" for c in criteria.values()), "待记录同批答卷的独立双评与分歧"),
    ]:
        if condition and not any(check["area"] == area and check["result"] == "pass" for check in review["checks"]):
            findings.append({"area": "assessment", "level": "pending", "message": message})
    return {
        "task_id": spec["task_id"], "revision": spec["revision"],
        "solver_snapshot_ready": not any(f["area"] == "contract" and f["level"] == "pending" for f in findings),
        "public_sha256": public_hashes,
        "assessment": {
            "mode": assessment_mode(criteria.values()) if scored else "unscored",
            "primary_mode": assessment_mode(primary) if scored else "unscored",
            "criteria_by_method": {m: [key for key, c in criteria.items() if c["method"] == m] for m in ("rule", "rubric")},
            "scorer": scorer, "recorded_checks": review["checks"],
        },
        "science": {
            "reference_policy": review["reference_policy"], "target_evidence": review["target_evidence"],
            "evidence": [{**item, "source_kinds": sorted(ancestry[key]), "sha256": file_digest(paths[key])}
                         for key, item in evidence.items()],
            "claims": claims, "baselines": review["baselines"],
        },
        "findings": findings,
    }
