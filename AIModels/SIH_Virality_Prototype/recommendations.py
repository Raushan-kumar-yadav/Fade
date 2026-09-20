def generate_recommendation(scores, baseline):
    q_score = int(scores["quality_score"] * 100)
    t_score = int(scores["text_score"] * 100)
    v_score = int(scores["virality_score"] * 100)
    
    explanation = "### Explanations & Recommendations\n\n"
    
    # 1. Creative Quality Breakdown
    explanation += f"**Creative Quality (Visual Aesthetics): {q_score}/100**\n"
    if q_score >= 70:
        explanation += "- ✅ *Excellent Thumbnail.* High human aesthetic appeal. Do not change the visual layout.\n"
    elif q_score >= 40:
        explanation += "- ⚠️ *Average Thumbnail.* Consider increasing contrast, saturation, or using clearer faces.\n"
    else:
        explanation += "- ❌ *Weak Thumbnail.* Visual appeal is low. A redesign is highly recommended before publishing.\n"
        
    explanation += "\n"
    
    # 2. Text/Title Breakdown
    explanation += f"**Title/Text Semantic Strength: {t_score}/100**\n"
    if t_score >= 60:
        explanation += "- ✅ *Strong Title.* Good use of keywords and semantic structure.\n"
    else:
        explanation += "- ⚠️ *Weak Title.* The text lacks semantic features typical of high engagement. Try making it more evocative or direct.\n"
        
    explanation += "\n"
    
    # 3. Context Breakdown
    explanation += f"**Audience Baseline Context:** {int(baseline):,} median views\n"
    explanation += "- *Note:* The virality model predicts relative outperformance. If your baseline is extremely high, outperforming it is mathematically harder.\n\n"
    
    # 4. Virality Breakdown
    explanation += "---\n"
    explanation += f"### Final Virality Prediction: {v_score}/100\n"
    if v_score >= 52:
        explanation += "**Status: HIGH POTENTIAL**\n"
        explanation += "The combined multimodal features suggest this content is likely to outperform your baseline."
    elif v_score >= 48:
        explanation += "**Status: AVERAGE POTENTIAL**\n"
        explanation += "The content aligns with standard historical performance."
    else:
        explanation += "**Status: LOW POTENTIAL**\n"
        explanation += "The content is predicted to underperform relative to your audience baseline."
        
    explanation += "\n\n> **⚠️ IMPORTANT SCIENTIFIC DISCLAIMER:**\n"
    explanation += "> *Creative Quality ≠ Actual Virality.* While we predict Human Visual Preference with high confidence (~0.68 AUC), the final Virality Prediction operates with **Low Confidence** (~0.53 AUC). Algorithmic reach depends heavily on luck, timing, and unobservable momentum factors. Use these scores as creative guidance, not guaranteed outcomes."
    
    return explanation
