import os
import pickle
import torch
import torch.nn as nn
from torchvision import models, transforms
from torchvision.models import ResNet18_Weights
from sentence_transformers import SentenceTransformer
import numpy as np

class SIHPipeline:
    def __init__(self, models_dir):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 1. Load PyTorch Models
        self.resnet = models.resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
        self.resnet.fc = nn.Identity()
        self.resnet = self.resnet.to(self.device)
        self.resnet.eval()
        
        self.sbert = SentenceTransformer('all-MiniLM-L6-v2', device=self.device)
        
        self.img_tf = transforms.Compose([
            transforms.Resize((256, 256)),
            transforms.CenterCrop((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])
        ])
        
        # 2. Load Scikit-Learn Pickles
        def load_pkl(name):
            with open(os.path.join(models_dir, name), 'rb') as f: return pickle.load(f)
            
        self.scaler_img = load_pkl("scaler_img.pkl")
        self.q_model = load_pkl("quality_model.pkl")
        self.scaler_txt = load_pkl("scaler_txt.pkl")
        self.t_model = load_pkl("text_model.pkl")
        self.ohe = load_pkl("ohe.pkl")
        self.scaler_ctx = load_pkl("scaler_ctx.pkl")
        self.meta_model = load_pkl("meta_model.pkl")
        
    def predict(self, image_pil, text, platform, category, baseline_views):
        # 1. Visual Feature
        img_t = self.img_tf(image_pil.convert("RGB")).unsqueeze(0).to(self.device)
        with torch.no_grad():
            img_feat = self.resnet(img_t).cpu().numpy()
            
        # 2. Text Feature
        text_feat = self.sbert.encode([text], convert_to_numpy=True)
        
        # 3. Stage 1 Scores
        q_score = self.q_model.predict_proba(self.scaler_img.transform(img_feat))[0, 1]
        t_score = self.t_model.predict_proba(self.scaler_txt.transform(text_feat))[0, 1]
        
        # 4. Context & Categories
        ctx = np.array([[np.log1p(baseline_views)]])
        ctx_scaled = self.scaler_ctx.transform(ctx)
        
        cat_arr = np.array([[platform.lower(), category]])
        cat_enc = self.ohe.transform(cat_arr)
        
        # 5. Final Meta-Model
        meta_features = np.hstack([[[q_score]], [[t_score]], ctx_scaled, cat_enc])
        v_prob = self.meta_model.predict_proba(meta_features)[0, 1]
        
        return {
            "quality_score": float(q_score),
            "text_score": float(t_score),
            "virality_score": float(v_prob),
            "meta_weights": self.meta_model.coef_[0].tolist(), # For explanations
            "meta_features": meta_features[0].tolist()
        }
