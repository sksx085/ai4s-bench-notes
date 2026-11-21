"""Task contract, public-file mapping, brief rendering and submission checks."""

import csv
import hashlib
import json
import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation


SECTIONS = {
    "overview": "Overview｜要做什么",
    "goal": "Goal｜目标",
    "background": "Background｜科学背景",
    "input": "Input｜可用资料",
    "output": "Output｜提交",
    "scoring": "Scoring｜怎样评阅",
    "constraints": "Constraints｜作答限制",
    "completion": "Completion criteria｜提交条件",
}
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
NETWORK_ACCESS = {"联网", "联网检索", "上网", "访问互联网", "浏览互联网", "访问外网", "使用互联网",
                  "internet", "internet access", "online access", "web browsing", "online search"}


class ContractError(ValueError):
    """An invalid artifact or contract."""


def text(value, location, blank=False):
    if not isinstance(value, str) or (not blank and not value.strip()):
        raise ContractError(f"{location} 应为{'可留空的' if blank else '非空'}字符串")
    return value


def obj(value, location):
    if not isinstance(value, dict):
        raise ContractError(f"{location} 应为对象")
    return value


def array(value, location):
    if not isinstance(value, list):
        raise ContractError(f"{location} 应为数组")
    return value


def choice(value, choices, location):
    if not isinstance(value, str) or value not in choices:
        raise ContractError(f"{location} 应取 {'、'.join(choices)} 之一")
    return value


def identifier(value, location):
    if not IDENTIFIER.fullmatch(text(value, location)):
        raise ContractError(f"{location} 应以小写字母开始，仅用小写字母、数字、下划线或连字符，最多 64 字符")
    return value


def number(value, location):
    if type(value) in (int, float):
        try:
            if math.isfinite(value):
                return value
        except OverflowError:
            pass
    raise ContractError(f"{location} 应为有限数")


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ContractError(f"{path}: JSON 键 {key} 重复")
            result[key] = value
        return result

    def bad_constant(value):
        raise ContractError(f"{path}: 无效 JSON 数字 {value}")

    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique, parse_constant=bad_constant,
                      parse_float=lambda value: number(float(value), str(path)))


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def relative(value):
    text(value, "路径")
    if ("\\" in value or ":" in value or any(ord(char) < 32 for char in value)
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise ContractError(f"使用工作区内的相对路径：{value!r}")
    return value


def local_file(root, name):
    path = root
    for part in relative(name).split("/"):
        path = path / part
        if path.is_symlink():
            raise ContractError(f"材料路径包含符号链接：{name}")
    if not path.is_file():
        raise ContractError(f"找不到文件：{name}")
    return path


def unique_paths(names):
    established = set()
    for name in names:
        key = unicodedata.normalize("NFC", relative(name)).casefold()
        if key in established:
            raise ContractError(f"文件名重复：{name}")
        established.add(key)
    for key in established:
        parts = key.split("/")
        if any("/".join(parts[:i]) in established for i in range(1, len(parts))):
            raise ContractError(f"文件与目录冲突：{key}")


def string_list(value, where):
    return [text(item, where) for item in array(value, where)]


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split()).rstrip(".。！!")


def rubric_levels(criterion, where):
    levels = obj(criterion.get("levels"), f"{where}.levels")
    if len(levels) < 2:
        raise ContractError(f"{where} 至少要提供两个可区分的评分等级")
    descriptions = set()
    for label, anchor in levels.items():
        identifier(label, where)
        description = normalized(text(anchor, f"{where}.levels.{label}"))
        if not description or description in descriptions:
            raise ContractError(f"{where} 的评分等级描述有空白或重复")
        descriptions.add(description)
    return levels


def validate_criteria(assessment):
    criteria = {}
    for criterion in array(assessment.get("criteria"), "assessment.criteria"):
        obj(criterion, "评分项")
        key = identifier(criterion.get("id"), "评分项 id")
        if key in criteria:
            raise ContractError(f"评分项 {key} 重复")
        text(criterion.get("description"), f"{key}.description")
        choice(criterion.get("role"), ("primary", "diagnostic"), f"{key}.role")
        method = choice(criterion.get("method"), ("rule", "rubric"), f"{key}.method")
        if method == "rule":
            text(criterion.get("rule"), f"{key}.rule")
            text(criterion.get("unit"), f"{key}.unit")
            choice(criterion.get("direction"), ("min", "max", "report"), f"{key}.direction")
        else:
            rubric_levels(criterion, key)
        criteria[key] = criterion
    return criteria


def validate_output(output):
    name = relative(output.get("path"))
    text(output.get("description"), name)
    if type(output.get("required")) is not bool:
        raise ContractError(f"{name}.required 应为 true 或 false")
    fmt = choice(output.get("format"), ("csv", "json", "file"), f"{name}.format")
    if fmt != "csv":
        return
    columns = {}
    for column in array(output.get("columns"), f"{name}.columns"):
        obj(column, name)
        field = text(column.get("name"), f"{name} 列名")
        if field != field.strip() or "\n" in field or "\r" in field or field in columns:
            raise ContractError(f"{name} 列名无效或重复：{field!r}")
        text(column.get("description"), f"{name}.{field}")
        kind = choice(column.get("type"), ("text", "number", "integer"), f"{name}.{field}.type")
        bounds = [number(column[k], f"{name}.{field}.{k}") for k in ("min", "max") if k in column]
        if bounds and (kind == "text" or (len(bounds) == 2 and bounds[0] > bounds[1])):
            raise ContractError(f"{name}.{field} 的取值范围无效")
        if kind != "text":
            text(column.get("unit"), f"{name}.{field}.unit")
        if "decimal_places" in column and (kind != "number" or type(column["decimal_places"]) is not int or column["decimal_places"] < 0):
            raise ContractError(f"{name}.{field}.decimal_places 应为非负整数，且列类型为 number")
        columns[field] = kind
    keys = string_list(output.get("key"), f"{name}.key")
    if not columns or not keys or len(set(keys)) != len(keys) or any(columns.get(k) != "text" for k in keys):
        raise ContractError(f"{name} 至少要声明一列，主键列应为已定义的文本列")
    if output.get("keys_from") is not None:
        relative(output["keys_from"])


def validate_spec(spec):
    obj(spec, "题目规格")
    if type(spec.get("schema_version")) is not int or spec["schema_version"] != 1:
        raise ContractError("schema_version 应为 1")
    identifier(spec.get("task_id"), "task_id")
    title = text(spec.get("title"), "title")
    if "\n" in title or "\r" in title:
        raise ContractError("title 应为单行")
    text(spec.get("revision"), "revision")
    sections = obj(spec.get("sections"), "sections")
    if unknown := sections.keys() - SECTIONS.keys():
        raise ContractError(f"sections 有未知字段：{'、'.join(sorted(unknown))}")
    for key, value in sections.items():
        text(value, f"sections.{key}", blank=True)
    constraints = obj(spec.get("constraints"), "constraints")
    network = choice(constraints.get("network"), ("offline", "allowed", "undecided"), "constraints.network")
    allowed = string_list(constraints.get("allowed"), "constraints.allowed")
    forbidden = string_list(constraints.get("forbidden"), "constraints.forbidden")
    allowed = {normalized(item) for item in allowed}
    forbidden = {normalized(item) for item in forbidden}
    if allowed & forbidden:
        raise ContractError(f"相同内容同时被允许和禁止：{'、'.join(sorted(allowed & forbidden))}")
    if network == "offline" and allowed & NETWORK_ACCESS:
        raise ContractError("题目要求断网，但允许项含明确的联网操作")
    public = obj(spec.get("public"), "public")
    if public.get("brief") is not None:
        relative(public["brief"])
    files = obj(public.get("files"), "public.files")
    unique_paths(["challenge.md", *files])
    for source in files.values():
        relative(source)
    outputs = [obj(row, "提交文件") for row in array(spec.get("submission"), "submission")]
    unique_paths([output.get("path") for output in outputs])
    for output in outputs:
        validate_output(output)
    assessment = obj(spec.get("assessment"), "assessment")
    criteria = validate_criteria(assessment)
    if assessment.get("scorer") is not None:
        relative(assessment["scorer"])
        args = string_list(assessment.get("score_args"), "assessment.score_args")
        if not any("{submission}" in arg for arg in args):
            raise ContractError("本地评分器的参数须以 {submission} 引用答卷目录")
    elif assessment.get("score_args"):
        raise ContractError("设置评分参数前应先接入评分器")
    for dependency in string_list(assessment.get("score_dependencies", []), "assessment.score_dependencies"):
        relative(dependency)
    relative(spec.get("review"))
    return criteria


def render_submission(output):
    required = "必交" if output["required"] else "选交"
    parts = [f"- `{output['path']}`（{required}）。{output['description']}"]
    if output["format"] != "csv":
        return parts
    fields = []
    for column in output["columns"]:
        kind = column["type"]
        details = {"number": ["有限数"], "integer": ["整数"], "text": ["非空文本"]}[kind]
        if kind != "text":
            details.insert(0, column["unit"])
        details += [f"{'≥' if key == 'min' else '≤'} {column[key]}" for key in ("min", "max") if key in column]
        if "decimal_places" in column:
            details.append(f"最多 {column['decimal_places']} 位小数")
        fields.append(f"  - `{column['name']}`（{'，'.join(details)}）。{column['description']}")
    parts.append("  - CSV 表头按以下列顺序填写。")
    parts.extend(fields)
    keys = "、".join(f"`{key}`" for key in output["key"])
    if source := output.get("keys_from"):
        parts.append(f"  - 仅填 `{source}` 中的 {keys}，每个组合一行。")
    else:
        parts.append(f"  - {keys} 的组合每个只填一行。")
    return parts


def render_criterion(criterion):
    description = criterion["description"]
    if criterion["method"] == "rubric":
        return [f"- {description}", *(f"  - {label}。{anchor}" for label, anchor in criterion["levels"].items())]
    direction = {"min": "越小越好", "max": "越大越好", "report": "描述量"}[criterion["direction"]]
    return [f"- {description}（{criterion['unit']}，{direction}）。{criterion['rule']}"]


def render(spec, additions=()):
    sections = {key: value.strip() for key, value in spec["sections"].items()}
    problem = [sections.get("goal") or "写明给定条件下要回答的问题。", sections.get("input", "")]
    if "background" in additions:
        background = [sections[key] for key in ("overview", "background") if sections.get(key)]
        if background:
            problem.extend(["### 背景", *background])
    outputs = spec["submission"]
    solution = [sections.get("output", "")]
    if outputs:
        solution.append("\n".join(line for output in outputs for line in render_submission(output)))
    elif not solution[0]:
        solution.append("写明要提交的结果及格式。")
    solution.append(sections.get("completion", ""))

    rules = spec["constraints"]
    network = {"offline": "断网作答。", "allowed": "可联网。", "undecided": "联网规则待确认。"}
    access = [network[rules["network"]]]
    forbidden = rules["forbidden"]
    if rules["network"] == "offline":
        forbidden = [item for item in forbidden if normalized(item) not in NETWORK_ACCESS]
    for items, label in ((rules["allowed"], "可使用"), (forbidden, "禁止")):
        if items:
            access.append(label + "、".join(items) + "。")
    constraints = ["".join(access)]
    constraints.extend(sections.get(key, "") for key in ("constraints", "scoring"))
    criteria = spec["assessment"]["criteria"]
    for role, heading in (("primary", "### 主评分"), ("diagnostic", "### 诊断评分")):
        if role == "diagnostic" and "diagnostics" not in additions:
            continue
        lines = [line for item in criteria if item["role"] == role for line in render_criterion(item)]
        if lines:
            constraints.extend([heading, "\n".join(lines)])
    body = [f"# {spec['title']}"]
    for heading, paragraphs in (("问题", problem), ("解答", solution), ("约束", constraints)):
        body.extend([f"## {heading}", *(p for p in paragraphs if p)])
    return "\n\n".join(body) + "\n"


def public_brief(spec, root, additions=()):
    if name := spec["public"].get("brief"):
        if additions:
            raise ContractError("交给工作台管理的精简题面才支持添加阅读内容。先整理题目规格再生成")
        return local_file(root, name).read_text(encoding="utf-8")
    return render(spec, additions)


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        header = next(reader, [])
        if not header or "" in header or len(set(header)) != len(header):
            raise ContractError(f"{path.name} 的 CSV 表头无效")
        rows = []
        for line, cells in enumerate(reader, 2):
            if len(cells) != len(header):
                raise ContractError(f"{path.name} 第 {line} 行列数不一致")
            rows.append(dict(zip(header, cells)))
    return header, rows


def unique_keys(rows, columns, filename):
    seen = set()
    for line, row in enumerate(rows, 2):
        key = tuple(row[k] for k in columns)
        if any(not cell or cell != cell.strip() for cell in key) or key in seen:
            raise ContractError(f"{filename} 第 {line} 行有空键、前后空白或重复键")
        seen.add(key)
    return seen


def expected_keys(output, path):
    header, rows = read_csv(path)
    keys = output["key"]
    if not rows or not set(keys).issubset(header):
        raise ContractError(f"{path.name} 应包含非空数据及键列 {', '.join(keys)}")
    return unique_keys(rows, keys, path.name)


def validate_csv(output, path, cases_path):
    header, rows = read_csv(path)
    if not rows or header != [c["name"] for c in output["columns"]]:
        raise ContractError(f"{path.name} 的表头或数据行不符合提交契约")
    keys = unique_keys(rows, output["key"], path.name)
    if cases_path:
        expected = expected_keys(output, cases_path)
        if keys != expected:
            raise ContractError(f"{path.name} 缺 {len(expected - keys)} 个键，多 {len(keys - expected)} 个键")
    for line, row in enumerate(rows, 2):
        for c in output["columns"]:
            value = row[c["name"]]
            field = f"{path.name} 第 {line} 行 {c['name']}"
            if c["type"] == "text":
                text(value, field)
                continue
            try:
                n = float(value)
            except ValueError as exc:
                raise ContractError(f"{field} 应填数字") from exc
            number(n, field)
            if c["type"] == "integer" and not re.fullmatch(r"[+-]?\d+", value.strip()):
                raise ContractError(f"{field} 应为整数")
            if n < c.get("min", -math.inf) or n > c.get("max", math.inf):
                raise ContractError(f"{field} 超出提交范围")
            if "decimal_places" in c:
                try:
                    exponent = Decimal(value).as_tuple().exponent
                except InvalidOperation as exc:
                    raise ContractError(f"{field} 无法按十进制精度核查") from exc
                if exponent < -c["decimal_places"]:
                    raise ContractError(f"{field} 超过 {c['decimal_places']} 位小数")
    return len(rows)
