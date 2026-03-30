#!/usr/bin/env python3
import argparse
import json
import math
import sqlite3
from difflib import SequenceMatcher
from typing import List, Dict, Tuple


def tokenize(text: str) -> List[str]:
    text = (text or "").replace("，", " ").replace(",", " ").strip()
    spaced = [t for t in text.split() if t]

    # 中文连写（无空格）时，仍做关键词切分
    has_space = (" " in text)
    if spaced and has_space:
        return spaced

    lexicon = ["职场", "内耗", "焦虑", "搞钱", "成长", "情绪", "解压", "女性", "关系", "副业", "通勤"]
    tokens = [w for w in lexicon if w in text]

    # 英文或确实无法切分时保留原词
    if spaced and not tokens:
        tokens.extend(spaced)

    if text and text not in tokens:
        tokens.append(text)
    return tokens


def build_base_sql(where_clause: str) -> str:
    return f"""
    WITH em_latest AS (
      SELECT e1.platform_episode_id, e1.play_count, e1.comment_count, e1.captured_at
      FROM episode_metrics_snapshot e1
      JOIN (
        SELECT platform_episode_id, MAX(captured_at) AS mx
        FROM episode_metrics_snapshot
        GROUP BY platform_episode_id
      ) t
      ON t.platform_episode_id = e1.platform_episode_id AND t.mx = e1.captured_at
    ),
    pm_latest AS (
      SELECT p1.platform_podcast_id, p1.subscribers, p1.captured_at
      FROM podcast_metrics_snapshot p1
      JOIN (
        SELECT platform_podcast_id, MAX(captured_at) AS mx
        FROM podcast_metrics_snapshot
        GROUP BY platform_podcast_id
      ) t
      ON t.platform_podcast_id = p1.platform_podcast_id AND t.mx = p1.captured_at
    )
    SELECT
      ei.podcast_name,
      ei.episode_title,
      ei.episode_desc,
      ei.episode_url,
      ei.release_date,
      em.play_count,
      em.comment_count,
      pm.subscribers
    FROM episode_index ei
    LEFT JOIN episode_platform_map epm ON epm.itunes_episode_id = ei.episode_id
    LEFT JOIN em_latest em ON em.platform_episode_id = epm.platform_episode_id
    LEFT JOIN podcast_platform_map ppm ON ppm.itunes_collection_id = ei.collection_id
    LEFT JOIN pm_latest pm ON pm.platform_podcast_id = ppm.platform_podcast_id
    WHERE {where_clause}
    """


def fetch_candidates(conn: sqlite3.Connection, topic: str, pool_limit: int, preferred_podcast: str = "", preferred_episode: str = "") -> List[Dict]:
    tokens = tokenize(topic)
    if not tokens:
        tokens = [topic.strip()] if topic.strip() else []

    parts = []
    params: List[str] = []

    if tokens:
        token_parts = []
        for tok in tokens:
            like = f"%{tok}%"
            token_parts.append("(ei.podcast_name LIKE ? OR ei.episode_title LIKE ? OR ei.episode_desc LIKE ?)")
            params.extend([like, like, like])
        parts.append("(" + " OR ".join(token_parts) + ")")

    if preferred_podcast:
        parts.append("ei.podcast_name LIKE ?")
        params.append(f"%{preferred_podcast}%")

    if preferred_episode:
        parts.append("ei.episode_title LIKE ?")
        params.append(f"%{preferred_episode}%")

    where_clause = " AND ".join(parts) if parts else "1=1"

    sql = build_base_sql(where_clause) + """
    ORDER BY COALESCE(em.play_count, 0) DESC,
             COALESCE(em.comment_count, 0) DESC,
             COALESCE(pm.subscribers, 0) DESC,
             ei.release_date DESC
    LIMIT ?
    """
    params.append(pool_limit)

    cur = conn.cursor()
    cur.execute(sql, tuple(params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def get_subscriber_quantiles(conn: sqlite3.Connection) -> Tuple[int, int]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT subscribers
        FROM podcast_metrics_snapshot
        WHERE subscribers IS NOT NULL
        ORDER BY subscribers ASC
        """
    )
    vals = [int(r[0]) for r in cur.fetchall() if r[0] is not None]
    if not vals:
        return 100000, 500000
    q1 = vals[max(0, int(len(vals) * 0.33) - 1)]
    q2 = vals[max(0, int(len(vals) * 0.66) - 1)]
    return q1, q2


def semantic_similarity(topic: str, row: Dict) -> float:
    corpus = f"{row.get('podcast_name','')} {row.get('episode_title','')} {row.get('episode_desc','')[:800]}"
    return SequenceMatcher(None, topic.lower(), corpus.lower()).ratio()


def keyword_hit_rate(tokens: List[str], row: Dict) -> float:
    if not tokens:
        return 0.0
    text = f"{row.get('podcast_name','')} {row.get('episode_title','')} {row.get('episode_desc','')}".lower()
    hits = sum(1 for t in tokens if t.lower() in text)
    return hits / max(1, len(tokens))


def heat_weight(subscribers: int, q1: int, q2: int) -> Tuple[float, str]:
    subs = int(subscribers or 0)
    # 小宇宙热度分层：S/A/B
    if subs >= q2:
        return 1.0, "S"
    if subs >= q1:
        return 0.7, "A"
    return 0.4, "B"


def score_rows(rows: List[Dict], topic: str, q1: int, q2: int) -> List[Dict]:
    tokens = tokenize(topic)
    scored = []
    for r in rows:
        sim = semantic_similarity(topic, r)
        hit = keyword_hit_rate(tokens, r)
        hw, tier = heat_weight(r.get("subscribers") or 0, q1, q2)
        score = 50 * sim + 20 * hit + 30 * hw
        out = dict(r)
        out.update({
            "semantic_similarity": round(sim, 4),
            "keyword_hit_rate": round(hit, 4),
            "heat_weight": hw,
            "heat_tier": tier,
            "score": round(score, 2),
            "score_formula": "Score = 50*semantic_similarity + 20*keyword_hit_rate + 30*heat_weight"
        })
        scored.append(out)
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--limit", type=int, default=5, help="最终返回条数")
    ap.add_argument("--pool-limit", type=int, default=80, help="初筛候选池大小")
    ap.add_argument("--podcast", default="", help="可选：指定播客名（模糊匹配）")
    ap.add_argument("--episode", default="", help="可选：指定单集名（模糊匹配）")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        cands = fetch_candidates(
            conn,
            topic=args.topic.strip(),
            pool_limit=max(args.limit, args.pool_limit),
            preferred_podcast=args.podcast.strip(),
            preferred_episode=args.episode.strip(),
        )
        q1, q2 = get_subscriber_quantiles(conn)
        scored = score_rows(cands, args.topic.strip(), q1, q2)[: args.limit]
        print(
            json.dumps(
                {
                    "topic": args.topic,
                    "constraints": {
                        "podcast": args.podcast,
                        "episode": args.episode,
                        "limit": args.limit,
                    },
                    "heat_tier_thresholds": {"A_min": q1, "S_min": q2},
                    "count": len(scored),
                    "items": scored,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
