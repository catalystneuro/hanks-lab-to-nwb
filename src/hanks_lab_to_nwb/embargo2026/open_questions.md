# Open Questions — Hanks Lab (WM & Bandit Tasks)

---

## 1. Subjects ✅ mostly resolved

| Field | Subject 400 | Subject 238 |
|---|---|---|
| Sex | M | M |
| Strain | Long Evans | Long Evans |
| Date of birth | 2024-03-19 | 2025-05-?? ⚠️ |
| Weight | 530 g | 540 g |

⚠️ **Subject 238 DOB** **[required]**: lab reported `2025-05-0` — please confirm the correct date
(currently using `2025-05-01` as a placeholder).

---

## 2. Session Metadata ✅ resolved

- **Timezone**: `America/Los_Angeles` (UC Davis) ✅
- **Experimenter**: Stevenson, Tanner ✅
- **Session descriptions**: approved ✅
- **Experiment description**: approved ✅
- **Keywords**: approved ✅
- **Related publication DOI**: unpublished — left blank ✅

---

## 3. Behavioral Setup ✅ resolved

- **Port assignments**: Port1 = left reward, Port2 = center poke, Port3 = right reward ✅
- **DIO04**: camera trigger ✅

---

## 4. Fiber Photometry Hardware ✅ mostly resolved

### Doric System ✅
- Fiber Photometry Console, 4-channel LED driver, 2× iFMC5 (ch 1-2) + 2× iFMC4 (ch 3-4) ✅
- **FPConsole software version** **[optional]**: not provided — can be added later

### Excitation Sources ✅
- Isosbestic: Doric Connecterized 415 nm LED, central 415 nm, FWHM 13 nm ✅
- Signal: Doric Connecterized 490 nm LED, central 490 nm, FWHM 26 nm ✅
- AOUT03 label discrepancy ("Ch3_420"): lab confirmed software labels are for display only,
  actual LED is 415 nm ✅
- **LED power at fiber tip** **[optional]**: not provided

### Optical Fibers ✅
- RWD R-FOC-BL400C-50NA, flat 400 µm, NA 0.5, 1.25 mm ceramic ferrule ✅
- Atlas: Paxinos & Watson, 7th edition, bregma reference ✅

### Photodetector ✅
- Doric iFMC minicube Si photodiode, gain 7.6 V/nW, sensitivity 350-1000 nm ✅
- Emission bandpass filter 500-550 nm → detected wavelength ~525 nm ✅
- Note: lab reported "960 nm peak" — that is the bare Si chip sensitivity peak,
  not the wavelength being detected through the 500-550 nm emission filter ✅

### Optical Filters ✅
- Emission: 500-550 nm (all channels) ✅
- Channels 1-2 excitation: ligand 470-493 nm, isosbestic 420-435 nm ✅
- Channels 3-4 excitation: ligand 460-490 nm, isosbestic 410-420 nm ✅
- Dichroic mirrors: integrated in minicube, model unknown ✅ (noted in metadata)

---

## 5. Viral Vector and Injection — partially open

Already have: injection coordinates, volume (500 nL), titer
(1.2×10¹³ VP/mL subj400, 6.1×10¹² VP/mL subj238).

- **Manufacturer**: UNC Vector Core ✅
- **Construct**: AAV9-CAG-dLight3.8 ✅
- **Titer units** **[required]**: lab reported VP/mL — NWB stores VG/mL. Are these
  VP (viral particles) or VG (viral genomes)? Please confirm so we can label correctly.
- **Injection dates per subject** **[optional]**: not provided
