#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_anchor_contexts.py

Google Colab-friendly script for generating natural anchor sentences
with a Qwen Instruct / Chat model from Hugging Face.

Recommended Colab setup:
    !pip install -q transformers accelerate sentencepiece

Example:
    !python generate_anchor_contexts.py \
        --input monosemy_corpus.json \
        --output monosemy_corpus_with_anchors.json \
        --model_name Qwen/Qwen2.5-3B-Instruct \
        --num_anchors 5
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


SYSTEM_PROMPT = """你是高质量中文词典例句生成助手。

任务：基于给定的“词语”和“释义”，生成自然、真实、可用作词典锚点的中文例句。

要求：
1. 每个句子都必须包含目标词语本身。
2. 必须严格依据给定释义造句，只体现这个词的词典本义。
3. 句子必须自然，像真实中文使用，而不是解释、定义或说明。
4. 不要写成以下风格：
   - “X一词通常指……”
   - “作为一个X……”
   - “X是指……”
   - 任何字典解释腔、百科腔、模板腔
5. 不要照抄参考例句，但可以借鉴它们的语体、搭配和场景。
6. 不要使用网络义、比喻义、饭圈义、引申义，除非释义本身就是这些义项。
7. 句子长度适中，尽量具体、自然，有生活场景。
8. 只输出 JSON 数组，不输出任何解释、标题或编号。

输出格式示例：
["例句一。", "例句二。", "例句三。"]
"""

USER_TEMPLATE = """请基于下面信息生成新的例句。

词语：{word}
释义：{meaning}
参考例句：
{contexts}

请生成 {num_anchors} 个新的中文例句。

再次强调：
- 任务是“基于 meaning 用 word 造句”
- 不是解释 meaning
- 不是改写释义
- 不是写模板句
- 每句都必须自然
- 每句都必须包含“{word}”
- 只返回 JSON 数组
"""

BAD_PATTERNS = [
    r"一词通常指",
    r"作为一个",
    r"作为一名",
    r"是一种",
    r"是一个",
    r"是指",
    r"如果你想成为",
    r"扮演着重要角色",
    r"本职工作",
    r"相关的技能",
    r"专注于",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to monosemy_corpus.json")
    parser.add_argument("--output", required=True, help="Path to save updated JSON")
    parser.add_argument(
        "--model_name",
        default="Qwen/Qwen2.5-3B-Instruct",
        help="Hugging Face Qwen model name",
    )
    parser.add_argument("--num_anchors", type=int, default=5)
    parser.add_argument("--max_new_tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top_p", type=float, default=0.9)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def load_json(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Input JSON must be a list.")
    return data


def save_json(path: str, data: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def merge_resume_data(
    original: List[Dict[str, Any]],
    existing: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    existing_map = {item.get("word"): item for item in existing if isinstance(item, dict)}
    merged = []
    for item in original:
        word = item.get("word")
        if word in existing_map and existing_map[word].get("anchor_contexts"):
            updated = dict(item)
            updated["anchor_contexts"] = existing_map[word]["anchor_contexts"]
            merged.append(updated)
        else:
            merged.append(item)
    return merged


def build_prompt(word: str, meaning: str, contexts: List[str], num_anchors: int) -> str:
    context_block = "\n".join(f"- {c}" for c in contexts) if contexts else "- 无"
    return USER_TEMPLATE.format(
        word=word,
        meaning=meaning,
        contexts=context_block,
        num_anchors=num_anchors,
    )


def load_model_and_tokenizer(model_name: str):
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype="auto",
        device_map="auto",
        trust_remote_code=True,
    )
    model.eval()
    return model, tokenizer


def extract_json_array(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def looks_bad(sentence: str, word: str, meaning: str) -> bool:
    if word not in sentence:
        return True
    for pattern in BAD_PATTERNS:
        if re.search(pattern, sentence):
            return True

    normalized_sentence = re.sub(r"\s+", "", sentence)
    normalized_meaning = re.sub(r"\s+", "", meaning)
    if normalized_meaning and normalized_meaning in normalized_sentence:
        return True

    if len(sentence) < max(6, len(word) + 2):
        return True

    return False


def parse_anchor_list(raw_text: str, word: str, meaning: str, expected_n: int) -> List[str]:
    cleaned_text = extract_json_array(raw_text)
    try:
        items = json.loads(cleaned_text)
    except Exception:
        return []

    if not isinstance(items, list):
        return []

    results = []
    for item in items:
        if not isinstance(item, str):
            continue
        sent = re.sub(r"\s+", " ", item).strip()
        if not sent:
            continue
        if looks_bad(sent, word, meaning):
            continue
        results.append(sent)

    results = list(dict.fromkeys(results))
    return results[:expected_n]


def generate_once(
    model,
    tokenizer,
    word: str,
    meaning: str,
    contexts: List[str],
    num_anchors: int,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
) -> List[str]:
    user_prompt = build_prompt(word, meaning, contexts, num_anchors)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    model_inputs = tokenizer([text], return_tensors="pt").to(model.device)

    with torch.no_grad():
        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=temperature,
            top_p=top_p,
            pad_token_id=tokenizer.eos_token_id,
        )

    output_ids = generated_ids[0][model_inputs["input_ids"].shape[1]:]
    output_text = tokenizer.decode(output_ids, skip_special_tokens=True)
    return parse_anchor_list(output_text, word, meaning, num_anchors)


def generate_anchor_contexts(
    model,
    tokenizer,
    word: str,
    meaning: str,
    contexts: List[str],
    num_anchors: int,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
) -> List[str]:
    attempts = [
        (temperature, top_p),
        (0.7, 0.9),
        (0.6, 0.85),
    ]

    best = []
    for temp, p in attempts:
        anchors = generate_once(
            model,
            tokenizer,
            word,
            meaning,
            contexts,
            num_anchors,
            max_new_tokens,
            temp,
            p,
        )
        if len(anchors) > len(best):
            best = anchors
        if len(best) >= max(3, min(5, num_anchors)):
            break

    return best


def main() -> None:
    args = parse_args()

    data = load_json(args.input)
    if args.resume:
        try:
            existing = load_json(args.output)
            data = merge_resume_data(data, existing)
        except FileNotFoundError:
            pass

    model, tokenizer = load_model_and_tokenizer(args.model_name)

    total = len(data)
    for i, entry in enumerate(data, start=1):
        word = entry.get("word", "")
        meaning = entry.get("meaning", "")
        contexts = entry.get("contexts", [])

        if entry.get("anchor_contexts"):
            print(f"[{i}/{total}] SKIP {word}")
            continue

        if not word or not meaning:
            entry["anchor_contexts"] = []
            save_json(args.output, data)
            print(f"[{i}/{total}] ERR malformed entry")
            continue

        anchors = generate_anchor_contexts(
            model=model,
            tokenizer=tokenizer,
            word=word,
            meaning=meaning,
            contexts=contexts if isinstance(contexts, list) else [],
            num_anchors=args.num_anchors,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
        )

        entry["anchor_contexts"] = anchors
        save_json(args.output, data)
        print(f"[{i}/{total}] OK  {word}: {len(anchors)} anchors")

    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
