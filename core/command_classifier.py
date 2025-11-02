# train_classifier.py
import numpy as np
import joblib
import re

class CommandClassifier:
    def __init__(self):
        self.pipeline = None
        self.classes_ = None
    
    def preprocess_text(self, text):
        """Proste czyszczenie tekstu"""
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)  # Usuwanie znaków interpunkcyjnych
        return text
    
    
    def predict(self, text):
        """Predykcja dla nowego tekstu"""
        if self.pipeline is None:
            raise ValueError("Model nie został wytrenowany!")
        
        processed_text = self.preprocess_text(text)
        prediction = self.pipeline.predict([processed_text])
        probability = self.pipeline.predict_proba([processed_text])
        
        return {
            'command': prediction[0],
            'confidence': np.max(probability[0]),
            'all_probabilities': dict(zip(self.pipeline.classes_, probability[0]))
        }
    
    @classmethod
    def load_model(cls, filepath):
        """Wczytanie modelu"""
        return joblib.load(filepath)