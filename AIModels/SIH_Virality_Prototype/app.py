import gradio as gr
from PIL import Image
from model_pipeline import SIHPipeline
from recommendations import generate_recommendation
import os

# Initialize Pipeline
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
try:
    pipeline = SIHPipeline(MODELS_DIR)
except Exception as e:
    pipeline = None
    print(f"Error loading models: {e}. Run export_weights.py first.")

def process_content(image, title, platform, category, baseline_views):
    if pipeline is None:
        return "Error: Models not loaded. Please run export_weights.py first.", 0, 0, 0
    
    # Process
    if image is None:
        return "Please upload a thumbnail/image.", 0, 0, 0
        
    scores = pipeline.predict(image, title, platform, category, baseline_views)
    explanation = generate_recommendation(scores, baseline_views)
    
    # Extract raw scores for the dials
    q_score = int(scores["quality_score"] * 100)
    t_score = int(scores["text_score"] * 100)
    v_score = int(scores["virality_score"] * 100)
    
    return explanation, q_score, t_score, v_score

# Gradio Interface
with gr.Blocks(theme=gr.themes.Soft(), title="SIH Virality Predictor") as demo:
    gr.Markdown("# 🚀 SIH Multimodal Virality & Quality Predictor")
    gr.Markdown("Upload content to analyze its **Human Creative Quality** and estimate its **Algorithmic Virality Potential**.")
    
    with gr.Row():
        with gr.Column(scale=1):
            image_in = gr.Image(type="pil", label="Thumbnail / Cover Image")
            title_in = gr.Textbox(label="Title / Caption", placeholder="Enter the video title or Instagram caption...", lines=2)
            platform_in = gr.Dropdown(choices=["youtube", "instagram"], value="youtube", label="Platform")
            category_in = gr.Dropdown(choices=["Entertainment", "Education", "Gaming", "People & Blogs", "Science & Technology", "Instagram_Content"], value="Entertainment", label="Category")
            baseline_in = gr.Number(value=10000, label="Creator Baseline Views (Historical Median)")
            submit_btn = gr.Button("Analyze Content", variant="primary")
            
        with gr.Column(scale=1):
            gr.Markdown("### Stage 1: Content Quality (High Confidence)")
            q_gauge = gr.Slider(0, 100, label="Creative Quality Score (Visual)", interactive=False)
            t_gauge = gr.Slider(0, 100, label="Title/Text Strength Score", interactive=False)
            
            gr.Markdown("### Stage 2: Algorithmic Prediction (Low Confidence)")
            v_gauge = gr.Slider(0, 100, label="Virality Potential Score", interactive=False)
            
            explanation_out = gr.Markdown(label="Explanations")

    submit_btn.click(
        fn=process_content,
        inputs=[image_in, title_in, platform_in, category_in, baseline_in],
        outputs=[explanation_out, q_gauge, t_gauge, v_gauge]
    )
    
    gr.Markdown("---")
    gr.Markdown("**Research Disclaimer:** This SIH prototype proves that *Creative Quality ≠ Actual Virality*. Creative quality (human aesthetic preference) is predicted with high confidence (~0.68 AUC). However, algorithmic virality relies heavily on timing, external promotion, and unobservable momentum factors, which limits prediction confidence (~0.53 AUC).")

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False)
