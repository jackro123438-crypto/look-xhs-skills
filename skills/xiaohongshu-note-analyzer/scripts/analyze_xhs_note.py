#!/usr/bin/env python3
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / 'references'


def load_ref(name: str) -> str:
    p = REFS / name
    return p.read_text(encoding='utf-8') if p.exists() else ''


def normalize_tags(tags_text: str):
    if not tags_text:
        return []
    parts = re.split(r'[\s,，]+', tags_text.strip())
    return [p if p.startswith('#') else f'#{p}' for p in parts if p]


def detect_sensitive(title: str, body: str):
    text = f"{title}\n{body}"
    patterns = {
        '高危': ['最有效', '绝对', '100%', '稳赚', '保证', '治愈', '根治'],
        '中危': ['赚钱', '副业', '引流', '加微信', '二维码', '返现', '暴富'],
        '低危': ['最好', '顶级', '无敌', '瘦十斤', '立马见效']
    }
    hits = []
    level = '安全'
    for lvl, words in patterns.items():
        for w in words:
            if w in text:
                hits.append(w)
                if lvl == '高危':
                    level = '高危'
                elif lvl == '中危' and level != '高危':
                    level = '中危'
                elif lvl == '低危' and level == '安全':
                    level = '低危'
    return level, sorted(set(hits))


def title_type(title: str):
    if re.search(r'\d', title):
        return '数字型'
    if '？' in title or '?' in title:
        return '痛点/提问型'
    if any(x in title for x in ['后悔', '震惊', '绝了', '太香了']):
        return '情绪型'
    return '普通陈述型'


def score_title(title: str):
    s = 5
    if 8 <= len(title) <= 20:
        s += 2
    if re.search(r'\d', title):
        s += 1
    if any(x in title for x in ['？', '?', '！', '!']):
        s += 1
    if any(x in title for x in ['怎么', '为什么', '原来', '居然', '后悔']):
        s += 1
    return min(s, 10)


def keyword_analysis(title: str, body: str, tags):
    words = re.findall(r'[\u4e00-\u9fffA-Za-z0-9]{2,}', f'{title} {body}')
    freq = {}
    for w in words:
        if len(w) < 2:
            continue
        freq[w] = freq.get(w, 0) + 1
    core = [k for k, _ in sorted(freq.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))[:5]]
    core_word = core[0] if core else ''
    positions = {
        'title': core_word in title if core_word else False,
        'body': core_word in body if core_word else False,
        'tags': any(core_word in t for t in tags) if core_word else False,
    }
    return core, positions


def business_score(text: str):
    s = 9
    lowered = text.lower()
    triggers = ['购买', '下单', '链接', '优惠', '折扣', '私信', '咨询', '品牌', '合作']
    count = sum(1 for t in triggers if t in lowered)
    s -= min(count * 2, 8)
    return max(s, 1)


def interaction_score(body: str):
    s = 5
    if any(x in body for x in ['你们觉得', '有人和我一样', '评论区', '你会吗', '你怎么看']):
        s += 3
    if any(x in body for x in ['收藏', '建议先码住', '清单', '合集', '教程', '步骤']):
        s += 2
    return min(s, 10)


def optimize_intro(core_word: str, title: str, body: str):
    first = body.strip().splitlines()[0] if body.strip() else ''
    suggestion = first
    if core_word and core_word not in first:
        suggestion = f'{core_word}这件事，我最近真的有点上头。{first}' if first else f'{core_word}这件事，我最近真的有点上头。'
    return suggestion[:80]


def main():
    ap = argparse.ArgumentParser(description='Analyze XiaoHongShu note content')
    ap.add_argument('--title', default='')
    ap.add_argument('--body', default='')
    ap.add_argument('--tags', default='')
    ap.add_argument('--input-json', default='')
    ap.add_argument('--format', choices=['markdown', 'json'], default='markdown')
    args = ap.parse_args()

    title, body, tags_text = args.title, args.body, args.tags
    if args.input_json:
        data = json.loads(Path(args.input_json).read_text(encoding='utf-8'))
        title = data.get('title', title)
        body = data.get('body', body)
        tags_text = ' '.join(data.get('tags', [])) if isinstance(data.get('tags'), list) else data.get('tags', tags_text)

    tags = normalize_tags(tags_text)
    sensitive_level, sensitive_hits = detect_sensitive(title, body)
    t_type = title_type(title)
    t_score = score_title(title)
    core, positions = keyword_analysis(title, body, tags)
    core_word = core[0] if core else '内容主题'
    b_score = business_score(f'{title}\n{body}\n{" ".join(tags)}')
    i_score = interaction_score(body)
    overall = round((t_score + b_score + i_score + (10 if sensitive_level == '安全' else 7 if sensitive_level == '低危' else 4 if sensitive_level == '中危' else 2)) / 4, 1)
    title_suggestions = load_ref('title-formulas.md')
    tag_advice = '标签数量合适' if 5 <= len(tags) <= 10 else '建议控制在 5-10 个标签'
    kw_layout = '✅' if all(positions.values()) else '❌'
    optimized_intro = optimize_intro(core_word, title, body)

    result = {
        'overall': overall,
        'core_keywords': core,
        'keyword_layout_ok': all(positions.values()),
        'title_type': t_type,
        'title_score': t_score,
        'risk_level': sensitive_level,
        'sensitive_hits': sensitive_hits,
        'business_score': b_score,
        'interaction_score': i_score,
        'optimized_intro': optimized_intro,
    }

    if args.format == 'json':
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    risk_emoji = {'安全': '🟢', '低危': '🟡', '中危': '🟠', '高危': '🔴'}[sensitive_level]
    print(f"# 小红书笔记分析报告\n")
    print(f"## 📊 综合评分: {overall}/10\n")
    print(f"## 1️⃣ 关键词分析\n- **核心关键词**: {', '.join(core) if core else '未明显识别'}\n- **关键词布局**: {kw_layout} 标题/正文/标签未完全覆盖，建议让核心词 `{core_word}` 同时出现在标题、首段、标签\n- **标签优化**: {tag_advice}\n")
    print(f"## 2️⃣ 标题/首段评估\n- **标题类型**: {t_type}\n- **吸引力评分**: {t_score}/10\n- **优化建议**: 标题尽量控制在 8-20 字，保留明确主题词，适当加入数字、反差或提问。\n")
    print(f"## 3️⃣ 敏感内容风险\n- **风险等级**: {risk_emoji} {sensitive_level}\n- **检测到的敏感词**: {', '.join(sensitive_hits) if sensitive_hits else '未检出明显高风险词'}\n- **修改建议**: 避免“绝对、100%、稳赚、治愈”这类强承诺词。\n")
    print(f"## 4️⃣ 商业化程度\n- **自然度评分**: {b_score}/10\n- **商业痕迹**: {'较弱，偏自然分享' if b_score >= 7 else '已有明显推荐/转化语气'}\n- **降低商业感建议**: 先讲故事和体验，再讲产品或结论。\n")
    print(f"## 5️⃣ 互动潜力\n- **讨论触发点**: {'✅ 有' if i_score >= 7 else '❌ 偏弱'}\n- **分享动机**: {'偏实用/共鸣' if i_score >= 7 else '建议补一句提问或态度表达'}\n- **收藏价值**: {i_score}/10\n")
    print(f"## 6️⃣ 优化后版本\n- **建议标题方向**: 围绕 `{core_word}` 保留主题词，增加反差、数字或提问。\n- **建议首段**: {optimized_intro}\n")
    print("## 📝 修改优先级\n1. 让核心关键词同时进入标题、首段、标签\n2. 删除强承诺/高风险表达\n3. 结尾补一个问题或明确互动钩子")
    if title_suggestions:
        print("\n---\n\n### 附：标题公式参考\n已接入 `references/title-formulas.md` 作为人工扩写参考。")


if __name__ == '__main__':
    main()
