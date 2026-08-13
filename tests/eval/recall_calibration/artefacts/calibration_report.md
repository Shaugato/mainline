# Recall calibration report

**SYNTHETIC CALIBRATION SET** - these numbers characterise the calibrator implementation, not the product.
**PRELIMINARY** - no customer-grade calibration is claimed at this checkpoint.

**Split policy:** `TB-2021-01-01-8ff35f2f`
**Fit folds:** 2019H1, 2019H2, 2020H1, 2020H2
**Evaluation folds:** 2021H1, 2021H2
**Calibrator digest:** `59cfe263f074af2b0ba7cf190fbec011b781944e1bac713756a3047006f4217f`
**Feature spec:** `9fa06c7afa0326d81c3b2b75f15e48adf014dec519f592ff2563c6ffb2328eb5`

**Brier:** 0.2086 | **ECE:** 0.1074 | **MCE:** 0.5000 | n = 180 (85 positive)

## Reliability diagram

| bin | n | mean predicted | observed | 95% interval | gap |
|---|---:|---:|---:|---|---:|
| [0.0, 0.1) | 3 | 0.0000 | 0.0000 | [0.0000, 0.5615] | +0.0000 |
| [0.1, 0.2) | 47 | 0.1552 | 0.1489 | [0.0741, 0.2769] | -0.0062 |
| [0.2, 0.3) | 31 | 0.2407 | 0.4194 | [0.2642, 0.5923] | +0.1786 |
| [0.3, 0.4) | 0 | - | - | - | - |
| [0.4, 0.5) | 37 | 0.4444 | 0.5135 | [0.3589, 0.6655] | +0.0691 |
| [0.5, 0.6) | 5 | 0.5337 | 0.6000 | [0.2307, 0.8824] | +0.0663 |
| [0.6, 0.7) | 18 | 0.6439 | 0.7778 | [0.5479, 0.9100] | +0.1339 |
| [0.7, 0.8) | 8 | 0.7143 | 1.0000 | [0.6756, 1.0000] | +0.2857 |
| [0.8, 0.9) | 29 | 0.8593 | 0.6897 | [0.5077, 0.8272] | -0.1697 |
| [0.9, 1.0) | 2 | 1.0000 | 0.5000 | [0.0945, 0.9055] | -0.5000 |

A gap whose Wilson interval straddles zero is not evidence of miscalibration at that band; a gap whose interval excludes zero is.
