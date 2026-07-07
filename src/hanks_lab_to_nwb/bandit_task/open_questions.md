# Open Questions — Bandit Task (ClassicRLTasks)

Questions marked **[required]** block NWB file generation.
Questions marked **[optional]** are recommended for DANDI but can be left blank.

---

## 1. Subjects

**Subject 400**
- Sex **[required]**: M / F
- Strain **[required]**: e.g. Long-Evans, Sprague-Dawley
- Date of birth **[optional]**: YYYY-MM-DD
- Weight at implant or experiment **[optional]**: e.g. "350 g"

**Subject 238**
- Sex **[required]**: M / F
- Strain **[required]**
- Date of birth **[optional]**: YYYY-MM-DD
- Weight **[optional]**

---

## 2. Session Metadata

- **Timezone** **[required]**: We assume `America/Los_Angeles` (UC Davis) — confirm or correct.
- **Experimenter names** **[required]**: Format "Last, First" for each person who ran sessions.
- **Session description** **[required]**: We propose the following for Bandit sessions — please correct or expand:

  > This session contains fiber photometry and behavioral data from a rat performing a two-arm
  > bandit task (ClassicRLTasks). On each trial, the rat initiates at the center port and chooses
  > either the left or right reward port. Reward probabilities are fixed within a block and switch
  > across blocks, requiring the animal to track reward history and update port preferences.
  > Behavioral events are controlled and recorded by Bpod. Fluorescence signals are acquired
  > simultaneously from up to four brain regions using a Doric system with dLight 3.8 (dopamine
  > indicator) at isosbestic and ligand excitation wavelengths.

- **Keywords** **[optional]**: We suggest: `dopamine`, `fiber photometry`, `reinforcement learning`,
  `decision making`, `bandit task`, `striatum`, `rat`, `dLight` — add or remove any.
- **Related publication DOI** **[optional]**: Format `doi:10.xxxx/xxxxx`; leave blank if unpublished.

---

## 3. Behavioral Setup

- **Port assignments** **[required]**: Bpod data contains Port1, Port2, Port3. Which is the
  center poke, left reward port, and right reward port?
- **DIO04** **[required]**: What is DIO04 in the Doric file used for? (DIO01 is the Bpod TTL sync.)

---

## 4. Fiber Photometry Hardware

Needed for `ndx-fiber-photometry`. Items marked **[required]** cannot be left blank.

### Doric System
- **System model / part number** **[required]**
- **FPConsole software version** **[optional]**

### Excitation Sources (three wavelengths in use: 420 nm, 415 nm, 490 nm)

> Note: The Doric file internally labels AOUT03 as "Ch3_420" but Subj Info lists 415 nm.
> Please confirm the actual excitation wavelength on AOUT03/AOUT04.

For each source: illumination type (LED/laser) **[required]**, manufacturer + model **[required]**,
exact center wavelength **[required]**, power at fiber tip in mW **[optional]**.

### Optical Fibers (flat 400 µm core, all implants)
- **Numerical aperture (NA)** **[required]**: e.g. 0.37, 0.48
- **Manufacturer and model / part number** **[required]**: e.g. "Doric MFC_400/430-0.48_FLT"

### Photodetector
- **Detector type** **[required]**: PMT / photodiode / other
- **Manufacturer and model** **[required]**
- **Detected wavelength (nm)** **[required]**: center wavelength this detector is configured for

### Optical Filters (emission filter, excitation filter, dichroic mirror) **[optional]**

---

## 5. Viral Vector and Injection

Already have: injection coordinates, volume (500 nL), titer (1.2×10¹³ VP/mL subj400,
6.1×10¹² VP/mL subj238).

Still needed:
- **Viral vector manufacturer** **[required]**: e.g. "Addgene", "UNC Vector Core"
- **Virus construct name** **[required]**: full name as in methods, e.g. "AAV9-CAG-dLight3.8"
- **Titer units** **[required]**: VP/mL or VG/mL? (NWB stores VG/mL)
- Injection date(s) per subject **[optional]**
