#!/usr/bin/env python3
from __future__ import annotations

import json

from deterministic_japanese_parser_mcp import AnalyzeRequest, ParserEngine

SAMPLES = [
    "まず確認する。",
    "危ない道を歩く。",
    "ぬいぐるみを買う。",
    "来るはずだ。",
    "確認せず進む。",
    "駅まで歩く。",
    "終わるまで待つ。",
    "ここでも使える。",
    "水でも飲む。",
    "雨でも行く。",
    "たらこを食べる。",
    "食べたら帰る。",
    "さよならを言う。",
    "必要なら進む。",
    "例えば、猫を挙げる。",
    "国際会議を開く。",
    "友達と、映画を見る。",
    "ボタンを押すと、画面が開く。",
    "雨が降りそうだ。",
    "天気予報によると雨が降るそうだ。",
    "彼は男らしい人だ。",
    "素晴らしい景色だ。",
    "かわいそうだ。",
    "彼は来るらしい。",
    "猫みたいだ。",
    "映画を見たい。",
    "実行するなら確認する。",
    "実行するな。",
    "以上のことから結論を出す。",
    "3個以上必要だ。",
    "以下の通りです。",
    "10個以下にする。",
    "ケーキが食べられる。",
    "先生に褒められる。",
    "雨のため試合を中止する。",
    "雨なので出かけない。",
    "入ってもよろしいですか？",
    "触っても大丈夫ですか？",
    "ここに置いても構いませんか？",
    "これでもいい？",
]


def main() -> None:
    engine = ParserEngine()
    rows = []
    for text in SAMPLES:
        response = engine.analyze(AnalyzeRequest(original_text=text))
        rows.append({
            "text": text,
            "tokens": [
                {
                    "surface": token.surface,
                    "normalized": token.normalized,
                    "pos": token.pos,
                    "span": [token.span.start, token.span.end],
                }
                for token in response.tokens
            ],
            "scopes": [
                {
                    "type": item.operator_type,
                    "value": item.semantic_value,
                    "marker": item.marker,
                    "span": [item.source_span.start, item.source_span.end],
                }
                for item in response.meaning_graph.reading_analysis.scope_operators
            ],
            "frames": [
                {
                    "predicate": frame.predicate,
                    "surface": frame.surface_predicate,
                    "voice": frame.voice,
                    "modality": frame.modality,
                    "polarity": frame.polarity,
                }
                for frame in response.meaning_graph.reading_analysis.predicate_frames
            ],
            "relations": [
                {
                    "relation": item.relation,
                    "marker": item.marker,
                }
                for item in response.meaning_graph.reading_analysis.discourse_relations
            ],
        })
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
