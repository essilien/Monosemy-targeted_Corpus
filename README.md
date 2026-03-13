# Monosemy-Targeted Corpus in Mandarin Chinese from Weibo Texts

## Overview

This repository provides resources and scripts for constructing a **monosemy-targeted corpus in Mandarin Chinese** from social media texts. The corpus is designed to support the research on [unrecorded word sense detection](https://github.com/essilien/Nonrecorded_Sense_Detection).

The dataset is built from posts on **Weibo**, a major Chinese microblogging platform where new linguistic usages frequently emerge. By focusing on words that are **monosemous in standard Chinese dictionaries**, the corpus enables the identification of contexts that may reflect **novel semantic extensions not yet recorded in lexicographic resources**.

---

## Data Source

All monosemous words are collected from **Baidu Dictionary**,one of the largest Chinese online dictionaries. The first 30 words are manually validated and the remaining 70 words are randomly selected.

All usage examples are collected from **Weibo**, one of the largest Chinese social media platforms.

Weibo posts are particularly suitable for this task because they contain:

- informal language
- emerging expressions
- creative semantic extensions
- large volumes of real-world usage data

Each collected post is treated as a usage context of the target word.

---

## Data Processing Pipeline

The corpus construction pipeline consists of four main stages.

### 1. Data Collection

Weibo posts containing the target words are retrieved through keyword-based search.

Each retrieved post is stored as a raw usage instance.

### 2. Data Cleaning

Raw social media texts contain substantial noise. The cleaning pipeline removes the following elements:

- hashtags (e.g. `#topic#`)
- user mentions (e.g. `@username`)
- hyperlinks
- multimedia placeholders (e.g. `某某的微博视频`)
- redundant whitespace and formatting artifacts

The goal is to preserve the linguistic context while removing platform-specific noise.

### 3. Context Extraction

For each post:

- the sentence containing the **target word** is extracted
- the cleaned sentence is stored as a **usage context**

Each instance contains:

- target word
- cleaned context sentence
- source platform

### 4. Synthetic Anchor Generation

To represent the **recorded dictionary sense**, the project generates **synthetic anchor contexts** using a large language model.

Anchor sentences are designed to clearly express the canonical dictionary meaning of the target word.

During later semantic clustering:

- clusters containing anchors are interpreted as **recorded-sense clusters**
- clusters without anchors are treated as **candidate unrecorded-sense clusters**

---

## Data Format

Each usage instance is stored as a JSON object.

Example:
```json
{
  "usage_id": "厨子_28",
  "target_word": "厨子",
  "context": "原来棍年这么带劲吗.. 冷圈遇上好厨子",
  "left_context": "原来棍年这么带劲吗.. 冷圈遇上好",
  "right_context": "",
  "source_platform": "Weibo"
}
```
### Core Fields

| Field | Description |
|------|-------------|
| `usage_id` | unique identifier for the usage instance |
| `target_word` | target word under investigation |
| `context` | full cleaned sentence containing the target word |
| `left_context` | text before the target word |
| `right_context` | text after the target word |
| `source_platform` | source platform (e.g. Weibo) |

### Additional Metadata

The dataset may include additional fields used during preprocessing and filtering, such as:

- `raw_text`
- `normalized_text`
- `target_start`
- `target_end`
- `is_duplicate`
- `is_short_context`
- `is_noisy`
- `is_named_entity_like`
- `topic_cluster_hint`
- `keep_for_analysis`

These fields are primarily used for **data cleaning and corpus construction** and may not be required for downstream experiments.

## Intended Use

This corpus is intended for research on:

- unrecorded word sense detection
- lexical semantic change
- word sense induction
- contextual embedding analysis
- social media linguistics

It is especially suitable for studies that compare **recorded dictionary senses** with **emerging online usages**.

---

## Limitations

Several limitations should be noted:

1. **Lexicographic monosemy does not always guarantee true semantic monosemy.**  
   Some words listed with a single dictionary sense may already exhibit unnoticed semantic variation.

2. **Social media text is noisy and highly dynamic.**  
   Even after cleaning, some contexts may remain ambiguous, incomplete, or pragmatically underspecified.

3. **Platform bias exists.**  
   Since the corpus is built from Weibo data, the observed usages may reflect platform-specific discourse rather than general Mandarin usage.

4. **Synthetic anchors are generated data.**  
   They serve as controlled semantic references, but they are not naturally occurring usage examples.

---

## Ethical Considerations

This project uses social media texts for research purposes. Users of this repository should take care to:

- comply with the terms of service of the original platform
- avoid redistributing sensitive personal information
- anonymize user-identifiable content when necessary
- use the data responsibly and only for legitimate research purposes
- may contain taboo language

---

## License

This dataset and accompanying scripts are intended for **research use only**.

Please ensure that your use of the data complies with applicable laws, institutional review requirements, and the platform policies of the original data source.

---

## Contact

For questions about the corpus construction pipeline or data format, please open an issue in this repository.
