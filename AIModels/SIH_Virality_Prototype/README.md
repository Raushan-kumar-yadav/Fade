# SIH Multimodal Virality Predictor (Prototype)

## Overview
This is the final inference application for the SIH problem statement. It demonstrates a scientifically rigorous **Two-Stage Cascading (Stacking) Architecture** that evaluates Youtube and Instagram content.

### Why a Two-Stage Model?
Our research uncovered a critical finding: **Creative Quality ≠ Actual Virality**. 
* **Stage 1 (High Confidence):** We successfully predict human visual preference (~0.68 AUC). This outputs the *Creative Quality Score*.
* **Stage 2 (Low Confidence):** Predicting *Actual Relative Virality* before publication is extremely difficult because algorithmic success relies on luck, timing, and momentum (~0.53 AUC). 

By separating these, the system provides creators with actionable design feedback (Quality) without making impossible promises about algorithmic luck (Virality).

## How to Run

1. Activate your virtual environment:
   ```bash
   .\venv\Scripts\activate
   ```
2. Navigate to this directory:
   ```bash
   cd sih_prototype
   ```
3. Run the Gradio App:
   ```bash
   python app.py
   ```
4. Open the local URL (usually `http://127.0.0.1:7860`) in your browser.

## Features
* **Multimodal Inputs:** Accepts Images (Thumbnails/Covers), Text (Titles/Captions), and Context (Creator Baseline Views, Platform, Category).
* **Frozen Transfer Learning:** Uses `ResNet18` (512d) and `SentenceTransformer` (384d) for robust feature extraction without overfitting.
* **Explainable AI:** Breaks down the final prediction into individual scores (Creative Quality, Text Strength) and provides text-based recommendations.
