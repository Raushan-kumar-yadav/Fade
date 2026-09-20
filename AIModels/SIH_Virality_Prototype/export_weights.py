import os
import json
import torch
import pickle
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, OneHotEncoder

BASE = r"C:\Users\ariji\OneDrive\Desktop\cnn testing"
FEATS_FILE = os.path.join(BASE, "experiment_9_sih_virality", "03_embeddings", "all_features.pt")
HUMAN_LABELS_FILE = os.path.join(BASE, "experiment_7_visual_robustness", "dataset.json")
TARGETS_FILE = os.path.join(BASE, "experiment_9_sih_virality", "02_target_construction", "virality_targets.json")
YT_RAW = os.path.join(BASE, "data", "quality", "metadata", "quality_dataset_raw.json")
OUT_DIR = os.path.join(BASE, "sih_prototype", "models")

def main():
    print("Loading datasets for final production export...")
    features = torch.load(FEATS_FILE, weights_only=False)
    with open(HUMAN_LABELS_FILE, "r", encoding="utf-8") as f: human_data = json.load(f)
    with open(TARGETS_FILE, "r", encoding="utf-8") as f: targets = json.load(f)
    with open(YT_RAW, "r", encoding="utf-8") as f: yt_raw = json.load(f)
    yt_cats = {item["video_id"]: item.get("category", "Unknown") for item in yt_raw}
    
    # 1. Train Quality Model (on 1933 human labels)
    q_vids = [i["video_id"] for i in human_data if i["video_id"] in features]
    q_labels = [1 if i["label"] == "GOOD" else 0 for i in human_data if i["video_id"] in features]
    q_X = np.array([features[v]["thumbnail"] for v in q_vids])
    
    scaler_img = StandardScaler()
    q_X_scaled = scaler_img.fit_transform(q_X)
    
    q_model = LogisticRegression(max_iter=1000, class_weight='balanced', C=0.1)
    q_model.fit(q_X_scaled, q_labels)
    
    # 2. Extract Full Data for Text & Meta Models
    vids, X_img, X_txt, X_ctx, platforms, categories, y_viral = [], [], [], [], [], [], []
    for vid, t in targets.items():
        if vid not in features: continue
        f = features[vid]
        
        vids.append(vid)
        X_img.append(f["thumbnail"])
        X_txt.append(f["title"] if "title" in f and f["title"].shape == (384,) else np.zeros(384))
        X_ctx.append([np.log1p(t["baseline"])])
        
        platforms.append(f.get("platform", "youtube"))
        categories.append(yt_cats.get(vid, "Instagram_Content"))
        y_viral.append(1.0 if t["relative_virality"] > 0 else 0.0)
        
    X_img = np.array(X_img)
    X_txt = np.array(X_txt)
    X_ctx = np.array(X_ctx)
    platforms = np.array(platforms)
    categories = np.array(categories)
    y_viral = np.array(y_viral)
    
    # 3. Train Text Model
    scaler_txt = StandardScaler()
    X_txt_scaled = scaler_txt.fit_transform(X_txt)
    
    t_model = LogisticRegression(max_iter=1000, class_weight='balanced', C=0.1)
    t_model.fit(X_txt_scaled, y_viral)
    
    # 4. Generate Stage 1 Scores
    q_scores = q_model.predict_proba(scaler_img.transform(X_img))[:, 1].reshape(-1, 1)
    t_scores = t_model.predict_proba(X_txt_scaled)[:, 1].reshape(-1, 1)
    
    # 5. Train Meta Model
    ohe = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    X_cat_enc = ohe.fit_transform(np.column_stack([platforms, categories]))
    
    scaler_ctx = StandardScaler()
    X_ctx_scaled = scaler_ctx.fit_transform(X_ctx)
    
    X_meta = np.hstack([q_scores, t_scores, X_ctx_scaled, X_cat_enc])
    
    meta_model = LogisticRegression(max_iter=1000, class_weight='balanced', C=0.1)
    meta_model.fit(X_meta, y_viral)
    
    # Save everything
    def save_pkl(obj, name):
        with open(os.path.join(OUT_DIR, name), 'wb') as f:
            pickle.dump(obj, f)
            
    save_pkl(scaler_img, "scaler_img.pkl")
    save_pkl(q_model, "quality_model.pkl")
    save_pkl(scaler_txt, "scaler_txt.pkl")
    save_pkl(t_model, "text_model.pkl")
    save_pkl(ohe, "ohe.pkl")
    save_pkl(scaler_ctx, "scaler_ctx.pkl")
    save_pkl(meta_model, "meta_model.pkl")
    
    print("Production models successfully exported!")

if __name__ == "__main__":
    main()
