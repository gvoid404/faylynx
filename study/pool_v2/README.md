# Building the bank_v2 prompt pool

These tools made `study/prompt_bank.json` (bank_v2, 1,000 prompts). They hold code only, no data.
They run against the private Paper 2 folder on Google Drive (`MyDrive/paper2-three-class/`); copy
the `.py` files into its `code/` folder first.

| File | What it does |
|---|---|
| `make_pool_v2_shadow.py` | Writes the 700 invented Shadow AI prompts (+70 spares), seed 20261120. All data made up. |
| `paper2_pool_v2_real.ipynb` | Colab: samples real Allow/Automated prompts from WildChat-4.8M (non-toxic), filters them, judge-labels them (rubric v3.1, hash c382d28af8), writes the review workbook, then builds the pool (cell 8). Includes every fix made while it was first run (restart-safe cells, long Automated prompts, control characters, quota shift). |
| `build_prompt_bank_v2b.py` | Assembles the pool from the Shadow part and the reviewed workbook: participant sets P01-P20 (40 each, 7/2/1 blocks) and the 200-prompt agent reserve. |
| `pool_v2_defang.py` | Rewrites the invented keys as documentation-style examples so GitHub push protection accepts the file. |
| `mask_secrets.py`, `test_mask_secrets.py` | Typed-placeholder masking of secrets and identifiers, used to filter real prompts; stdlib only. |
| `paper2_retrain_masked.py` | Retrains the content model with and without masking on the verified Shadow AI set (non-sealed split only). |

Order: `make_pool_v2_shadow.py`, then the notebook cells 1-7, hand review of `audit/pool_v2_review.xlsx`, then cell 8.
