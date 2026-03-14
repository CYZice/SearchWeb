import re
import argparse
from docx import Document

FIELD_MAP = {
    "器名": "name",
    "时代": "era",
    "時代": "era",
    "别称": "alias",
    "別稱": "alias",
    "出土": "discovery",
    "发现": "discovery",
    "發現": "discovery",
    "现藏": "collection",
    "現藏": "collection",
    "著录": "publication",
    "著錄": "publication",
    "形制": "format",
    "释文": "transcript",
    "釋文": "transcript",
}

record_pattern = re.compile(r"^[【$$](\d+)[】$$]")
field_pattern = re.compile(r"^([^\s：:]+)[\s]*[：:](.*)")

def short(s, n=80):
    s = s.replace("\n", "\\n").replace("\r", "")
    return s if len(s) <= n else s[:n] + "..."

def inspect(docx_path, targets):
    doc = Document(docx_path)
    current_record = None
    current_field = None
    in_targets = False
    print(f"FILE: {docx_path}")
    print(f"TARGETS: {sorted(targets)}")
    print("=" * 120)

    for i, para in enumerate(doc.paragraphs, 1):
        raw = para.text.strip()
        m = record_pattern.match(raw)
        if m:
            current_record = m.group(1).zfill(3)
            current_field = None
            in_targets = current_record in targets
            if in_targets:
                print(f"\n[RECORD {current_record}] paragraph#{i} marker={short(raw, 40)}")
            continue

        if not in_targets:
            continue

        fm = field_pattern.match(raw)
        key_raw = fm.group(1).strip() if fm else None
        mapped = None
        if key_raw:
            for k, v in FIELD_MAP.items():
                if k in key_raw:
                    mapped = v
                    break

        if mapped:
            current_field = mapped

        has_hyperlink = bool(para._p.xpath(".//*[local-name()='hyperlink']"))
        br_count = len(para._p.xpath(".//*[local-name()='br']"))
        run_texts = [r.text for r in para.runs if r.text]
        merged_run_text = "".join(run_texts)

        print(f"\nP#{i} len={len(raw)} style={para.style.name if para.style else ''} field={key_raw or '-'} mapped={mapped or '-'} current_field={current_field or '-'} br={br_count} hyperlink={has_hyperlink}")
        print(f"TEXT: {short(raw, 200)}")

        if fm and mapped == "name":
            v = fm.group(2).strip()
            print(f"NAME_VALUE len={len(v)} sample={short(v, 120)}")
            if len(v) > 30 or any(x in v for x in "，。；：！？"):
                print("WARN: name 值过长或包含大量正文标点，疑似“器名段混入释文正文”。")

        if (not fm) and current_field == "name":
            print("WARN: 当前段无法识别字段，且 current_field=name；旧逻辑会把该段续写到 name。")

        if merged_run_text:
            print(f"RUN_MERGED: {short(merged_run_text, 200)}")

    print("\n" + "=" * 120)
    print("检查重点：")
    print("1) 是否出现 field=器名 且 NAME_VALUE 很长（像正文）")
    print("2) 是否出现 br>0 且同一段同时含“器名”和大段正文")
    print("3) 是否 hyperlink=False（说明蓝色下划线不是原始链接，而是前端把 name 渲染成了链接样式）")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--docx",
        default=r"d:\Microsoft VS Code\lidan\search_web\data\raw_word\☆辽代墓志（太宗-興宗）.docx",
    )
    parser.add_argument("--ids", default="071,072")
    args = parser.parse_args()
    ids = {x.strip().zfill(3) for x in args.ids.split(",") if x.strip()}
    inspect(args.docx, ids)