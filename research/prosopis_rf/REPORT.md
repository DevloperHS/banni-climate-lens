# Is a Thorny Tree Making Banni Greener?

**A study of Prosopis and plant greenness in Banni grassland, Kutch, India (2001 to 2024)**

| | |
|---|---|
| Date of work | 13 November 2026 |
| Tools | Google Earth Engine Code Editor (project `banni-trend-2026`), checked again with the Earth Engine Python API |
| Script studied | `banni_rf.js` (copy in `gee/banni_rf.js`) |
| Where the numbers come from | Every number in this report comes from a file in `results/`. None were typed in by hand. |

## Contents

1. [The short answer](#1-the-short-answer)
2. [Words you will meet](#2-words-you-will-meet)
3. [The question](#3-the-question)
4. [What we checked before starting](#4-what-we-checked-before-starting)
5. [How we did it](#5-how-we-did-it)
6. [What we found](#6-what-we-found)
7. [What it means](#7-what-it-means)
8. [What this study cannot tell us](#8-what-this-study-cannot-tell-us)
9. [What to do next](#9-what-to-do-next)
10. [Files](#10-files)
11. [Sources and credits](#11-sources-and-credits)

---

## 1. The short answer

**No. The thorny tree (Prosopis) is not the main reason Banni is getting greener.**

* Banni's plants have become greener every rainy season since 2001.
* Part of that comes from rain. But even after we take the rain away, the land is still getting greener.
* We expected that if Prosopis were the cause, only places **with** Prosopis would get greener.
* Instead, places with **no trees or bushes at all**, only salty ground and small plants, are getting greener too.
* Every kind of land is getting greener at about the **same pace: roughly 20 % more green every 10 years**.
* That points to something that touches **the whole landscape**, not to the tree.
* Places with Prosopis do gain a little more green, so the tree may **add** to the greening where it grows. It just does not **cause** it.
* When we **take the Prosopis woodland out** of the area, the greening trend of what is left changes by less than 13 %. By the project's 25 % rule, that is a **neutral** effect.
* We do not yet know what the landscape-wide cause is. Farming, wetter soil, less salty soil, changes in grazing, or rain patterns we could not measure are all still possible.

---

## 2. Words you will meet

| Word | What it means here |
|---|---|
| **Banni** | A large grassland in Kutch, Gujarat, India. It is flat, dry and in many places salty. |
| **Prosopis** (*Prosopis juliflora*) | A thorny tree brought to Kutch in the 1960s. It spreads fast and is pushing out grass. |
| **Satellite image** | A photo of the Earth taken from space. |
| **Pixel** | One small square in a satellite image, like one tile in a mosaic. |
| **NDVI** | A greenness score worked out from satellite pictures. Bare ground is close to 0. Thick green forest is close to 0.9. |
| **MODIS** | A NASA satellite camera. Its pixels are 250 m wide (about two football fields). We used it for greenness from 2001 to 2024. |
| **Sentinel-2** | A European satellite camera. Its pixels are 10 m wide (about a small house). We used it to make the Prosopis map. |
| **Random forest** | A computer method that learns to sort things into groups by looking at examples. Here it learns to tell Prosopis from water, grass and salty land. |
| **Training points** | Example spots we labelled by hand ("this spot is Prosopis") so the computer can learn. |
| **Land types (classes)** | The four groups on our map: **Prosopis woodland** (thick trees), **mixed** (scattered Prosopis bushes with grass), **water or wetland**, and **saline brushland** (salty ground with only small low plants, no trees). |
| **Monsoon** | The rainy season, June to September. |
| **CHIRPS** and **IMERG** | Two different records of how much rain fell. Using both checks that our answer does not depend on one record. |
| **Trend** | Whether something goes up or down over many years. |
| **Trend per year (Sen slope)** | How much the greenness score goes up each year, on average. For example, +0.0063 per year adds up to +0.15 over 24 years. |
| **Per decade** | Every 10 years. |
| **p-value** | A number that tells us how likely the pattern is to be a fluke. **Smaller is stronger.** Scientists usually call a pattern real when p is below 0.05 (1 chance in 20). |
| **Significant** | The pattern passed that test (p below 0.05). |
| **Rain removed** | We worked out how much greenness each year's rain explains, took that part away, and looked at what was left. If the leftover still rises, something other than rain is helping. |
| **Accuracy** | The share of test spots the map got right. 0.96 means 96 out of 100. |
| **Kappa** | Like accuracy, but it does not give credit for lucky guesses. 1 is perfect, 0 is no better than guessing. |
| **ROI** (region of interest) | The box of land we studied: 69.0 to 69.9 degrees East, 23.4 to 23.9 degrees North. |
| **Asset** | A file saved inside Earth Engine so it can be reused later. |

---

## 3. The question

Satellites show that Banni has been getting greener for more than 20 years. Rain alone does not explain all of it.

One idea is that **Prosopis is spreading**. Trees are greener than grass, so more trees would make the land look greener from space.

The project brief gives a simple rule to test this:

> If the greening is only where Prosopis is, Prosopis is the likely reason. If the greening is in both places, the reason is something else.

So we needed to:

1. Make a map showing where Prosopis is.
2. Split the land into "lots of Prosopis" and "little or no Prosopis".
3. Check whether both kinds of land got greener from 2001 to 2024, with and without the effect of rain.

---

## 4. What we checked before starting

Before doing new work, we checked the claims already made about the project.

| Claim | Is it true? | How we know |
|---|---|---|
| The earlier result (+0.0017 per year, p = 0.0059) can be made again | Yes | All 9 figures in the handover came out the same from `data/processed` |
| The project uses real data, not made-up data | Yes | Download records, live runs and exact repeats of the numbers |
| Some older numbers in the documents were wrong | Yes | Now corrected in the `docs/` files |
| There is no well (groundwater) data; the `water_table` file is really water loss from plants (ET) and soil moisture | Yes | Its label also wrongly said NDVI. Fixed in `backend/app/gee/extract.py`, with a test added |
| The study box is 9,751 km2, while Banni itself is about 2,500 km2 | Yes | `regions.json` and published figures |
| Thick Prosopis grew from 1.4 % (2014) to 13.8 % (2023) | Cannot be checked | These numbers are not in the field data files. A news report (Mongabay) on the same study gives about +2,000 hectares instead. Our own 2023 map shows 11.6 % Prosopis woodland, a similar size for 2023, but we have no 2014 value |
| Very wet years such as 2020 confuse the greenness score | Partly true | 2020 is the wettest rainy season in both rain records (CHIRPS 524 mm, IMERG 1,001 mm) |

---

## 5. How we did it

### Step 1: Teach the computer what each land type looks like

A random forest learns from examples, so we had to give it good ones.

1. A program suggested **378 possible spots** using a world land-cover map (ESA WorldCover 2021) and the same Sentinel-2 picture the script uses.
2. **We looked at every spot by eye** on a sharp aerial photo (Esri World Imagery, where each pixel is about 1 m). Each photo covered about 330 m, with the script's 20 m circle drawn on it.
3. We kept or relabelled **159** spots. We threw the rest away: edges between two land types, roads, farm fields, villages, and spots we were not sure about. Every decision is written down in `labelling/visual_labels.csv`.
4. To know what each land type really looks like, we compared with **10 field sites visited by scientists** (Bhan 2024). Saline brushland looks like pale, open, flat ground with a few low shrubs. Mixed land looks like scattered Prosopis bushes over grass or bare ground.
5. We dropped any spot closer than **150 m** to another spot or to a field site, so the same patch is never counted twice.

**Final count:** 39 Prosopis woodland, 34 mixed, 53 water or wetland and 33 saline brushland. Every type has at least 30, as the task asked. These are in `labelling/training_points.csv` and, ready to paste into Earth Engine, in `gee/manual_points.js`.

> Note: the brief asked for Google's aerial photos. We used Esri's instead, because computer programs are not allowed to read Google's photos. Both are very sharp and taken at about the same time.

### Step 2: Check how good the map is

We tested the map in two ways.

| Test | Accuracy | Kappa |
|---|---|---|
| The script's own test in the Code Editor, run 1 (30 % of **pixels** kept aside) | **0.966** | **0.948** |
| The same test, later runs | 0.961 | 0.948 and 0.954 |
| The same test, run again in Python | 0.960 to 0.965 | 0.946 to 0.953 |
| A stricter test: 30 % of **whole spots** kept aside, repeated 5 times (`scripts/06_point_holdout_accuracy.py`) | **0.763** (0.720 to 0.816) | 0.682 |

A picture of the Code Editor result is in `results/code_editor_console_accuracy.jpg`.

**Why are the two tests so different?** The script's own test is a bit like a school test that uses questions copied from the homework. Its test pixels sit right next to the pixels the computer learned from, so of course it gets them right. That gives **96 %**, which passes the 80 % goal.

The stricter test hides **whole spots** the computer has never seen. That is a fairer exam, and it gives **76 %**, just below the goal.

What the stricter test tells us about each land type:

* **Prosopis woodland:** reliable. It was found 63 % to 100 % of the time, and when the map said "Prosopis" it was right 71 % to 98 % of the time.
* **Water:** almost always right.
* **Mixed versus saline brushland:** this is the weak spot. The computer often mixes these two up.

Small changes between runs (0.961 versus 0.966) come from Earth Engine picking test pixels at random. Nothing was changed between runs.

**Problems found in the field sites the script uses** (`banni_rf.js`, step A):

* The script says a site should count only if at least 65 % of it is one land type. Three sites it uses fail this rule: LTM_10 (64.5 %), LTM_18 (59 %) and LTM_26 (56 %). Two sites that pass, LTM_11 and LTM_23, are not used.
* LTM_29 is labelled saline brushland, but the aerial photo shows thick trees right on the spot.
* LTM_36 sits on a railway line. LTM_10 is next to a village and a pond.

### Step 3: Make the table of greenness and rain

The script is meant to save a table (CSV file) with one row per year, giving the greenness of high-Prosopis pixels, the greenness of low-Prosopis pixels, and the rain.

**The script as received could not do this.** Earth Engine stopped with the message `Reprojection output too large (14637x5634 pixels)`. Two other fixes we tried also failed (`User memory limit exceeded`, then `Execution failed; out of memory`).

**Why it failed:** the script rebuilt the detailed 10 m map again for every one of the 24 years, on top of MODIS's 250 m grid. Near Banni, MODIS's grid is tilted, so each step needed a strip of the 10 m map about **146 km wide**. That was too big for Earth Engine.

**How we fixed it, without changing any rule or threshold:**

1. `gee/stage1_classmap.js` makes the 2023 Prosopis map **once** and saves it as an asset (`projects/banni-trend-2026/assets/banni_rf_classmap_2023`). This used about 6.8 hours of Earth Engine computer time.
2. `gee/stage2_table.js` reads that saved map instead of rebuilding it, and splits the work into smaller pieces (`tileScale: 16`). It then saved the table to Google Drive as `banni_ndvi_by_prosopis_chirps.csv`.

We opened the file from Google Drive and saved it on this computer. We also worked out the same table again in full detail from the same saved map. The two matched almost perfectly (they differ by less than one part in a billion). Copies are in `data/extras/prosopis_rf/` and `results/`.

### Step 4: Test the trends

For each group of pixels we:

1. Took the average greenness for each rainy season (June to September) from 2001 to 2024, using only good-quality MODIS pictures.
2. Tested whether it went up over the years (Hamed-Rao Mann-Kendall test, with the Sen slope for how fast).
3. Did the same test again after removing the effect of rain, once with CHIRPS rain and once with IMERG rain.

The program for this is `scripts/05_analyse_trends.py`, and its results are in `results/trend_tests.json`.

---

## 6. What we found

### 6.1 What the land is made of (2023 map)

| Land type | Share of the study box |
|---|---|
| Prosopis woodland | 11.6 % |
| Mixed Prosopis and grass | 45.9 % |
| Water or wetland | 13.6 % |
| Saline brushland | 29.0 % |

The map is in `results/rf_classmap_2023.png`.

Using the script's rules, we sorted the MODIS pixels into two groups:

* **High Prosopis:** more than 40 % Prosopis woodland. There are **8,763** such pixels. On average they are 65 % woodland and 33 % mixed.
* **Low Prosopis:** less than 5 % Prosopis woodland. There are **43,105** such pixels. About half are mixed and half are saline brushland.

Both groups leave out pixels that are 10 % or more water.

### 6.2 Did both groups get greener?

**Yes, both did.**

| What we measured | Trend 2001 to 2024 | After removing CHIRPS rain | After removing IMERG rain |
|---|---|---|---|
| Greenness, high-Prosopis pixels | +0.0063 per year, p = 0.002 | +0.0034 per year, p = 0.021 | +0.0032 per year, p = 0.027 |
| Greenness, low-Prosopis pixels | +0.0048 per year, p = 0.0003 | +0.0029 per year, p = 0.003 | +0.0026 per year, p = 0.004 |
| Difference between the two (high minus low) | +0.0015 per year, **p = 0.063 (not significant)** | | |
| Rainy-season rain (CHIRPS) | +7.3 mm per year, p = 0.21 (not significant) | | |

**In plain words:**

* Both groups got greener, and both stayed greener after rain was taken away.
* High-Prosopis land got greener a little faster, but the difference is too small to be sure it is real (p = 0.063 is above 0.05).
* Rain itself did not clearly go up over the years.

A second way of removing rain (a model of greenness from rain and year together) gave the same answer: +0.0041 per year (p = 0.006) for high-Prosopis pixels and +0.0033 per year (p = 0.0005) for low-Prosopis pixels, using CHIRPS.

### 6.3 Do the two rain records agree?

They go up and down together from year to year (correlation r = 0.95, where 1 would be perfect). But IMERG's amounts are about **1.8 times** CHIRPS's (an average of 526 mm against 288 mm; in 2020, 1,001 mm against 524 mm).

The two records cover slightly different boxes, but that is far too small to explain almost double the rain. This backs up an issue already listed in `docs/KNOWN_ISSUES.md`: IMERG seems too high over Kutch and should be checked against India's weather service (IMD).

**The greening answer is the same whichever rain record we use.**

### 6.4 Does the answer change if we change the rules?

We re-ran the test with different cut-off values and with a map from an earlier year (`scripts/09_robustness.py`, results in `results/robustness_tests.json`). "Rain removed" here uses CHIRPS.

| Rules used | High / low pixels | High Prosopis, rain removed | Low Prosopis, rain removed | Difference, high minus low |
|---|---|---|---|---|
| 2023 map, 40 % / 5 % (the script's own rules) | 8,763 / 43,105 | +0.0034 per year, p = 0.021 | +0.0029 per year, p = 0.003 | +0.0015 per year, p = 0.063 |
| 2023 map, 30 % / 10 % | 11,806 / 47,336 | +0.0035 per year, p = 0.027 | +0.0030 per year, p = 0.004 | +0.0014 per year, **p = 0.040** |
| 2023 map, 50 % / 2 % | 6,447 / 39,063 | +0.0034 per year, p = 0.035 | +0.0029 per year, p = 0.008 | +0.0016 per year, p = 0.087 |
| 2017 map, 40 % / 5 % | 7,881 / 44,716 | +0.0039 per year, p = 0.027 | +0.0030 per year, p = 0.004 | +0.0019 per year, p = 0.070 |

**In plain words:**

* Both groups got greener under every set of rules, with and without rain.
* High-Prosopis land was always a little faster, but the difference passed the p below 0.05 test only once, with the loosest rules.
* The 2017 map (the same computer model used on a November 2016 to March 2017 picture, saved as `banni_rf_classmap_2017`) gives the same picture. So the result is not just a side effect of choosing pixels that happened to look green in 2023.

### 6.5 The deciding test: land with no trees or bushes at all

There was still one gap. The "low Prosopis" group is about half **mixed** land, which still has scattered Prosopis bushes. Maybe those bushes were growing thicker and making that land greener.

So we picked out pixels that are almost entirely **saline brushland**: at least 90 % salty brushland, no Prosopis woodland, and less than 10 % mixed. The strictest group had to pass this test on **both** the 2017 and the 2023 maps. We compared them with the tree groups (`scripts/10_brush_vs_woody.py`, results in `results/brush_vs_woody_tests.json`).

| Group (2023 map) | MODIS pixels | Average greenness | Trend | Pace (relative) | After removing CHIRPS rain | After removing IMERG rain |
|---|---|---|---|---|---|---|
| Pure saline brushland | 13,216 | 0.105 | +0.0022 per year, p = 0.004 | +21 % per decade | +0.0017 per year, p = 0.002 | +0.0014 per year, p = 0.002 |
| Pure brushland in 2017 **and** 2023 | 11,270 | 0.106 | +0.0022 per year, p = 0.004 | +20 % per decade | +0.0016 per year, p = 0.001 | +0.0014 per year, p = 0.002 |
| Brushland, looser rule (at least 80 %) | 15,462 | 0.115 | +0.0028 per year, p below 0.001 | +24 % per decade | +0.0020 per year, p = 0.001 | +0.0016 per year, p = 0.002 |
| Mixed (at least 80 %) | 16,401 | 0.307 | +0.0060 per year, p = 0.003 | +19 % per decade | +0.0033 per year, p = 0.021 | +0.0024 per year, p = 0.018 |
| Prosopis woodland (more than 40 %) | 8,763 | 0.356 | +0.0063 per year, p = 0.002 | +18 % per decade | +0.0034 per year, p = 0.021 | +0.0032 per year, p = 0.027 |

Differences between groups:

* Woodland minus pure brushland: +0.0040 per year, p = 0.024 (pure in both years: p = 0.021). **Significant.**
* Woodland minus mixed: p = 0.33. **Not significant.**

**In plain words:**

* Land with **no trees or bushes in 2017 or 2023** is getting greener, and the trend is **even clearer** once rain is removed (p = 0.001 to 0.002).
* Tree land gains more greenness points per year. But tree land is also about three times greener to start with.
* Compared with how green each kind of land already is, **every group rises at about the same pace: 18 % to 24 % every 10 years.**
* Think of it like pocket money. If every child in a class gets a 20 % raise, the child who had more money gets more coins, but nobody's raise is special. That looks like a change for everyone, not a change caused by one thing.
* Woodland and mixed land behave the same.

### 6.6 Taking Prosopis out: does the area's trend change?

The tests above compare groups. This one asks the question the other way round: **if we remove the Prosopis pixels from the area, how much does the area's greening trend change?** (`scripts/11_remove_prosopis.py`, results in `results/remove_prosopis_tests.json`).

The rule was fixed before running:

* **Positive effect:** removing Prosopis lowers the trend by 25 % or more, or the trend is no longer significant. (Prosopis was pushing the trend up.)
* **Negative effect:** removing Prosopis raises the trend by 25 % or more. (Prosopis was holding the trend down.)
* **Neutral:** the change is less than 25 % and the trend is still significant.

All series use the study box and leave out watery pixels, as before.

| What is left | MODIS pixels | Average greenness | Trend | Pace (relative) | Change after removing CHIRPS rain | Change after removing IMERG rain | Effect |
|---|---|---|---|---|---|---|---|
| Everything (the starting point) | 69,093 | 0.259 | +0.0054 per year, p = 0.0003 | +21 % per decade | +0.0033 per year, p = 0.012 | +0.0028 per year, p below 0.0001 | |
| Without the high-Prosopis pixels (woodland more than 40 %) | 60,330 | 0.245 | +0.0051 per year, p = 0.0003 | +21 % per decade | **-3.5 %** (still p = 0.006) | **+0.2 %** (still p = 0.006) | **Neutral** |
| Without any pixel that has 5 % or more woodland | 43,105 | 0.216 | +0.0048 per year, p = 0.0003 | +22 % per decade | **-12.8 %** (still p = 0.003) | **-6.2 %** (still p = 0.004) | **Neutral** |
| Without any trees **or** scattered bushes (only bare salty brushland left) | 13,231 | 0.105 | +0.0022 per year, p = 0.004 | +21 % per decade | -48.7 % (still p = 0.002) | -49.5 % (still p = 0.002) | Rule says "positive", but see below |

**In plain words:**

* Taking out the **Prosopis woodland** barely changes the trend (less than 13 %). **Prosopis woodland has a neutral effect.**
* The last row drops by about half. But that row throws away **four out of every five pixels**, including all the grassy mixed land, and keeps only bare salty ground that is about **2.5 times less green** to begin with. Less green land can only gain fewer greenness points.
* Its **pace** is exactly the same as everything else: **+21 % per decade**. So the drop is caused by what kind of land is left, not by losing Prosopis.
* The "mixed" land is scattered Prosopis bushes **plus grass**, so removing it removes grass as well. This test cannot split the two apart. The fair reading is: **Prosopis woodland, neutral; scattered Prosopis in grass, cannot be told apart from the grass.**

---

## 7. What it means

* **The greening is everywhere.** It shows up in land with lots of Prosopis, in land with little Prosopis, and in land with no trees or bushes at all.
* **It is not just rain.** It is still there after removing rain, using two separate rain records.
* **It grows at the same pace everywhere** compared with how green each place already is.
* By the project brief's own rule ("if the trend is in both places, the reason is something else"), **Prosopis is not the reason Banni is greener than its rain explains.** Something that affects the whole landscape is.
* Prosopis land does gain a little more green in absolute terms, so the tree may **add** some greening where it grows.

---

## 8. What this study cannot tell us

* **What the real cause is.** We showed what it is not, not what it is.
* **Farming.** The map has **no farmland class**. Farms in mainland Kutch (the south part of the study box) get filed as mixed or Prosopis. So we cannot test the "new fields" idea from the brief.
* **Soil.** In very bare places (greenness around 0.1), wetter or less salty soil can raise the greenness score even without more plants.
* **The weak spot of the map.** "Pure brushland" depends on telling brushland apart from mixed land, which is where the map is least reliable (see Step 2).
* **Rain in more complicated ways.** We removed rain with a straight-line method. Effects of rain timing, or of very wet and very dry years acting differently, are not ruled out.
* **The past.** Land with little Prosopis in 2023 might have had Prosopis before and had it cleared, or might have small bushes too tiny for 250 m pixels to show. The 2017 map gives the same answer, which helps. But the 2017 map uses a model trained on 2023 examples, and nobody has checked how accurate it is.
* **A small extra Prosopis effect.** Prosopis land was a little faster in every version of the test, but significantly so in only one. A small extra boost from Prosopis cannot be ruled out.
* **The exact Banni border.** The study box is a rectangle. It includes part of mainland Kutch and the edge of the Rann (salt desert), not just Banni.

---

## 9. What to do next

1. **Add a farmland class** (and possibly an open grassland class) to the map and run everything again. Without it, the "fields" question cannot be answered.
2. **Add more examples of mixed land and saline brushland** until the stricter accuracy test passes 80 %.
3. **Check the 2017 map's accuracy** with examples labelled on 2017 photos.
4. **Use the real Banni border** instead of a rectangle, once a border map is available.

---

## 10. Files

All paths are inside `research/prosopis_rf/` unless they start with `data/`, `docs/` or `backend/`.

| File | What it is |
|---|---|
| `gee/banni_rf.js` | The script as received, unchanged |
| `gee/manual_points.js` | The hand-labelled points, ready for Earth Engine |
| `gee/banni_rf_with_points.js` | Points plus script: what was run first to get accuracy and kappa |
| `gee/stage1_classmap.js` | Makes and saves the 2023 map |
| `gee/stage2_table.js` | Makes the greenness and rain table from the saved map |
| `labelling/candidates*.csv` | The possible spots suggested by the computer (three rounds) |
| `labelling/visual_labels.csv` | Our by-eye decision on every spot |
| `labelling/training_points.csv` | The final 159 points |
| `scripts/01_candidate_points.py` to `scripts/06_point_holdout_accuracy.py` | Each step, in order |
| `scripts/09_robustness.py` | The tests with different rules and the 2017 map |
| `scripts/10_brush_vs_woody.py` | The no-trees test |
| `scripts/11_remove_prosopis.py` | The "take Prosopis out" test with the 25 % rule |
| `results/code_editor_console_accuracy.jpg` | Picture of the accuracy result in the Code Editor |
| `results/rf_accuracy_python.json`, `results/rf_accuracy_point_holdout.json` | Accuracy results |
| `results/class_shares_2023.json`, `results/rf_classmap_2023.png` | Land-type shares and the map |
| `results/banni_ndvi_by_prosopis_chirps*.csv` | The greenness and rain table (Drive copy and full-detail copy) |
| `results/trend_tests.json` | Main trend results |
| `results/robustness_tests.json`, `results/robustness_series.csv` | Results with different rules |
| `results/brush_vs_woody_tests.json`, `results/brush_vs_woody_series.csv` | No-trees test results |
| `results/remove_prosopis_tests.json`, `results/remove_prosopis_series.csv` | "Take Prosopis out" test results |
| `data/extras/prosopis_rf/` | Local copies of the table |
| `docs/KNOWN_ISSUES.md` | Known problems, including the three found in this work |

How to run every step again is in [README.md](README.md).

---

## 11. Sources and credits

* **Field sites:** Bhan (2024), field survey dataset of Banni grassland, Zenodo, [doi:10.5281/zenodo.11197850](https://doi.org/10.5281/zenodo.11197850). CC BY 4.0.
* **Aerial photos for labelling:** Esri World Imagery (Maxar, Earthstar Geographics).
* **Satellite and rain data** (through Google Earth Engine): MODIS MOD13Q1 version 6.1 (NASA), Sentinel-2 (European Space Agency, Copernicus), ESA WorldCover 2021, CHIRPS daily rainfall (UC Santa Barbara Climate Hazards Center), IMERG rainfall (NASA).
* **Statistics:** `pymannkendall` (Hamed-Rao Mann-Kendall test and Sen slope) and `statsmodels` (removing rain).
