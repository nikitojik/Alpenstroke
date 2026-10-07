# Evaluation: apertus-v1.5-8b

2026-10-07T17:14:28, 3 repeat(s), endpoint `http://host.docker.internal:8080/v1`
prompts: parse `7e3e4f30`, analysis `8b462d23`, plan `47f3ef80`

## parse

| metric | value |
|---|---|
| runs | 81 |
| valid_output | 88% |
| first_try | 43% |
| median_seconds | 15.8 |
| course | 100% |
| duration | 59% |
| effort | 75% |
| intervals | 48% |
| sets | 72% |
| symptoms | 85% |
| total | 75% |
| all_correct | 20% |
| by_split | dev: 21%, holdout: 20%, test: 17% |
| by_language | de: 25%, en: 17%, fr: 50%, it: 25%, ru: 0% |

## analysis

| metric | value |
|---|---|
| runs | 9 |
| valid_output | 100% |
| first_try | 100% |
| median_seconds | 15.2 |
| expected_found | 100% |
| grounded | 100% |
| nothing_forbidden | 100% |
| all_correct | 100% |
| by_profile | cramps: 100%, spike: 100%, steady: 100% |

## plan

| metric | value |
|---|---|
| runs | 9 |
| valid_output | 89% |
| first_try | 33% |
| median_seconds | 52.1 |
| cautions_present | 50% |
| final_within_target | 100% |
| goal_stroke_kept | 100% |
| grounded | 100% |
| model_within_target | 0% |
| rules_ok | 75% |
| all_correct | 67% |
| by_profile | cramps: 33%, spike: 67%, steady: 100% |
