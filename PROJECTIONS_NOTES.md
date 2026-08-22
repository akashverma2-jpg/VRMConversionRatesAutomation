# Projections & Pacing Multipliers Notes

This document captures the sanity check findings, recommendations for projection methodology improvements, and a comparison of new pacing multipliers computed using incremental months (May, June, and July 2026).

---

## 1. Sanity Check & Recommendations

### Finding A: Dynamic Denominator Mismatch
*   **The Issue**: The current dashboard applies a `Math.max(anchorRate, projectedRate)` floor to all projections, assuming MTD cumulative rates can only grow.
*   **Analysis**: This is mathematically true for **Favourite** rates because the denominator (pool size of 5585) is fixed. However, for **Activation** and **Consolidated** rates, the denominator (Inactive Supply) grows dynamically. If supply increases faster than sales, MTD rates can and do drop.
*   **Recommendation**: Allow the Activation and Consolidated projection lines to drop if pacing trends indicate a mid-month dip (remove the `Math.max` floor).

### Finding B: Early-Day Volatility
*   **The Issue**: Multipliers are extremely large in the first few days of the month. If the first 2-3 days have a small sample size anomaly (e.g., 1 sale out of 2 quotes = 50% rate), the month-end projection balloons to unrealistic numbers.
*   **Recommendation**: Hide projection lines or show a warning overlay until **Day 5** of the month.

### Finding C: Distortion from Outliers
*   **The Issue**: Pacing matrices are calculated using the **arithmetic mean (average)** of growth rates. A single highly anomalous historical month will skew the projection.
*   **Recommendation**: Transition to using the **median** growth multiplier instead of the average.

---

## 2. Multipliers Comparison (Old vs. New)

Below is a comparison of Consolidated, Activation, and Favourite multipliers showing the shift after adding the incremental data from May, June, and July 2026.

### Consolidated Rate Multipliers
| Transition | Dataset | Base Multiplier | Bear (Low) | Bull (High) | Months ($n$) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Day 3 ➔ Day 31** | **Old** <br> **New** | 6.7533 <br> **7.8405** *(+16%)* | 5.9208 <br> **6.0019** | 7.3083 <br> **9.6792** | 5 <br> **6** |
| **Day 3 ➔ Day 29** | **Old** <br> **New** | 6.4511 <br> **7.0981** *(+10%)* | 5.3716 <br> **5.3716** | 7.5307 <br> **8.4793** | 8 <br> **9** |
| **Day 2 ➔ Day 15** | **Old** <br> **New** | 5.5531 <br> **6.1368** *(+10%)* | 4.4771 <br> **4.9847** | 6.2704 <br> **7.2889** | 5 <br> **6** |
| **Day 1 ➔ Day 16** | **Old** <br> **New** | 26.4819 <br> **25.1921** *(-5%)* | 12.2606 <br> **12.2606** | 40.7032 <br> **34.8907** | 6 <br> **7** |

### Activation Rate Multipliers
| Transition | Dataset | Base Multiplier | Bear (Low) | Bull (High) | Months ($n$) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Day 1 ➔ Day 26** | **Old** <br> **New** | 2.9168 <br> **2.6129** *(-10%)* | 2.5747 <br> **1.8585** | 3.2590 <br> **3.1158** | 4 <br> **5** |
| **Day 2 ➔ Day 26** | **Old** <br> **New** | 3.0454 <br> **2.7641** *(-9%)* | 2.2297 <br> **1.9549** | 3.8612 <br> **3.5732** | 8 <br> **10** |
| **Day 1 ➔ Day 19** | **Old** <br> **New** | 2.5954 <br> **2.3191** *(-11%)* | 2.1589 <br> **1.5162** | 3.0318 <br> **2.8543** | 4 <br> **5** |

### Favourite Rate Multipliers
| Transition | Dataset | Base Multiplier | Bear (Low) | Bull (High) | Months ($n$) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Day 3 ➔ Day 31** | **Old** <br> **New** | 11.6169 <br> **13.1896** *(+13.5%)* | 10.2143 <br> **10.6532** | 12.5520 <br> **15.7261** | 5 <br> **6** |
| **Day 2 ➔ Day 29** | **Old** <br> **New** | 16.3510 <br> **17.2472** *(+5.5%)* | 13.9494 <br> **14.3488** | 18.1522 <br> **20.1456** | 7 <br> **8** |
| **Day 1 ➔ Day 30** | **Old** <br> **New** | 63.1803 <br> **61.4633** *(-3%)* | 39.5884 <br> **39.5884** | 86.7722 <br> **77.8695** | 6 <br> **7** |

---

## 3. How to Update in Dashboard (For Future Reference)
To apply these new multipliers in the dashboard, the static `const HISTORY` array at the top of the script tag in [mtd_dashboard.html](file:///Users/akashverma/Documents/ConvAutomationAndReporting/vrm_mtd_conv_rates/vrm_mtd_conv_rates/mtd_dashboard.html) must be updated to append the parsed daily records for `2026-05`, `2026-06`, and `2026-07`. The matrices (`MM_CONS`, `MM_ACT`, `MM_FAV`) can then be updated with the recalculated outputs.
